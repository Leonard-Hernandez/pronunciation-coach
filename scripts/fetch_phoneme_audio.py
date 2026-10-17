"""Download human IPA recordings from Wikimedia Commons for the phoneme guide.

Run once (needs network and ffmpeg), then commit the result:

    uv run python scripts/fetch_phoneme_audio.py

For each guide symbol listed in ``SOURCES`` the script:

1. asks the Wikipedia API which audio files the lead section (the IPA infobox) of the
   sound's article embeds, and takes the first one, or the listed preference after
   checking that the article really embeds it (no guessed filenames);
2. reads the file's Commons description and license metadata, and refuses anything
   that is not CC0, public domain, CC BY or CC BY-SA;
3. checks that the description names the expected IPA sound;
4. converts it with ffmpeg + numpy: mono, 48 kHz, high-pass 60 Hz, leading/trailing
   silence trimmed, RMS-normalized to -20 dBFS (peak capped at -1 dBFS), 10 ms fades,
   encoded as Ogg/Opus 64 kb/s;
5. writes ``src/pronunciation_coach/static/phonemes/<slug>.ogg``, ``attribution.json``
   (read by the server) and ``ATTRIBUTION.md`` (for people).

Sounds without a good Commons recording (diphthongs, unstressed /ɚ/) are not listed:
the app plays their example word with Piper instead.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "src" / "pronunciation_coach" / "static" / "phonemes"
USER_AGENT = "pronunciation-coach/0.1 (offline pronunciation practice app; one-time fetch of IPA samples) python-urllib"
WIKI_API = "https://en.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
AUDIO_EXT = (".ogg", ".oga", ".opus", ".wav", ".flac", ".mp3")
FREE_LICENSE = re.compile(r"^(CC0|Public domain|PD\b|CC BY(-SA)? \d\.\d)", re.I)

RATE = 48000
TARGET_RMS_DB = -20.0
PEAK_DB = -1.0
TRIM_DB = -40.0  # relative to the loudest 10 ms frame
KEEP_SECONDS = 0.06  # silence kept before and after the sound
FADE_SECONDS = 0.01
# upload.wikimedia.org rate-limits bursts hard (HTTP 429): pause between downloads.
DOWNLOAD_PAUSE = 8.0

# symbol -> (Wikipedia article, preferred infobox file or None, IPA the description must name)
SOURCES: dict[str, tuple[str, str | None, str]] = {
    # vowels
    "i": ("Close front unrounded vowel", None, "i"),
    "ɪ": ("Near-close near-front unrounded vowel", None, "ɪ"),
    "ɛ": ("Open-mid front unrounded vowel", None, "ɛ"),
    "æ": ("Near-open front unrounded vowel", None, "æ"),
    "ɑ": ("Open back unrounded vowel", None, "ɑ"),
    "ɔ": ("Open-mid back rounded vowel", None, "ɔ|Open-mid vowels"),
    "ʌ": ("Open-mid back unrounded vowel", None, "ʌ"),
    "ʊ": ("Near-close near-back rounded vowel", None, "ʊ"),
    "u": ("Close back rounded vowel", None, "u"),
    "ə": ("Mid central vowel", None, "ə"),
    # r-colored: "er" as said in US English (a stressed /ɝ/ on its own)
    "ɝ": ("R-colored vowel", "En-us-er.ogg", "US English"),
    # consonants (most recordings are [Ca aCa])
    "p": ("Voiceless bilabial plosive", None, "p"),
    "b": ("Voiced bilabial plosive", None, "b"),
    "t": ("Voiceless dental and alveolar plosives", "Voiceless_alveolar_plosive.ogg", "t"),
    "d": ("Voiced dental and alveolar plosives", "Voiced_alveolar_plosive.ogg", "d"),
    "k": ("Voiceless velar plosive", None, "k"),
    "ɡ": ("Voiced velar plosive", None, "ɡ|g"),
    "tʃ": ("Voiceless postalveolar affricate", None, "tʃ|t͡ʃ|postalveolar affricate"),
    "dʒ": ("Voiced postalveolar affricate", None, "dʒ|d͡ʒ|postalveolar affricate"),
    "f": ("Voiceless labiodental fricative", None, "labiodental fricative"),
    "v": ("Voiced labiodental fricative", None, "labiodental fricative"),
    "θ": ("Voiceless dental fricative", None, "θ"),
    "ð": ("Voiced dental fricative", "Voiced_dental_fricative.ogg", "ð"),
    "s": ("Voiceless alveolar fricative", None, "s"),
    "z": ("Voiced alveolar fricative", None, "z"),
    "ʃ": ("Voiceless postalveolar fricative", None, "ʃ"),
    "ʒ": ("Voiced postalveolar fricative", None, "ʒ"),
    "h": ("Voiceless glottal fricative", "Voiceless_glottal_fricative.ogg", "h"),
    "m": ("Voiced bilabial nasal", None, "m"),
    "n": ("Voiced dental and alveolar nasals", "Alveolar_nasal.ogg", "n"),
    "ŋ": ("Voiced velar nasal", None, "ŋ"),
    "l": ("Voiced dental and alveolar lateral approximants", "Alveolar_lateral_approximant.ogg", "l"),
    "ɹ": ("Voiced alveolar approximant", None, "ɹ"),
    "j": ("Voiced palatal approximant", None, "j"),
    "w": ("Voiced labial–velar approximant", None, "w"),
    "ɾ": ("Voiced dental and alveolar taps and flaps", "Alveolar_tap.ogg", "ɾ"),
    # Spanish sounds the recognizer may hear
    "a": ("Open front unrounded vowel", None, "a"),
    "e": ("Close-mid front unrounded vowel", None, "e"),
    "o": ("Close-mid back rounded vowel", None, "o"),
    "x": ("Voiceless velar fricative", None, "x"),
    # Spanish intervocalic 'b' is an approximant, [β̞]
    "β": ("Voiced bilabial fricative", "Bilabial_approximant.ogg", "β"),
}


# ------------------------------------------------------------------- API helpers
def fetch_url(url: str) -> bytes:
    """GET with retries; honours Retry-After on HTTP 429 (Commons rate-limits bursts)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 5:
                raise
            wait = float(exc.headers.get("Retry-After") or 5 * 2 ** attempt)
        except OSError:
            if attempt == 5:
                raise
            wait = 2 ** attempt
        time.sleep(min(wait, 120))
    raise AssertionError("unreachable")


def api(base: str, **params) -> dict:
    query = urllib.parse.urlencode({**params, "format": "json", "formatversion": 2})
    return json.loads(fetch_url(f"{base}?{query}"))


def infobox_audio(article: str) -> tuple[str, list[str]]:
    """Resolved article title and the audio files its lead section (infobox) embeds."""
    page = api(WIKI_API, action="parse", page=article, prop="images", section=0, redirects=1)["parse"]
    return page["title"], [f for f in page["images"] if f.lower().endswith(AUDIO_EXT)]


def commons_file(name: str) -> dict:
    title = "File:" + name.replace("_", " ")
    page = api(COMMONS_API, action="query", titles=title, prop="imageinfo|revisions",
               iiprop="url|extmetadata|mime|size", rvprop="content", rvslots="main")["query"]["pages"][0]
    if "imageinfo" not in page:
        raise SystemExit(f"{title}: not found on Commons")
    info = page["imageinfo"][0]
    wikitext = page["revisions"][0]["slots"]["main"]["content"]
    meta = {k: v.get("value", "") for k, v in info["extmetadata"].items()}
    return {"title": page["title"], "info": info, "meta": meta, "wikitext": wikitext}


def plain(html: str) -> str:
    text = re.sub(r"<[^>]+>", "", html or "")
    return re.sub(r"\s+", " ", text).strip()


def author_of(f: dict) -> str:
    """'Recorded by X' from the description, else the Artist field, else the first uploader."""
    m = re.search(r"Recorded by \[\[(?:user|User):([^|\]]+)(?:\|([^\]]+))?\]\]", f["wikitext"])
    if m:
        return (m.group(2) or m.group(1)).strip()
    m = re.search(r"Recorded by ([A-Z][\w .-]+?)[.\n]", plain(f["meta"].get("ImageDescription", "")) + "\n")
    if m:
        return m.group(1).strip()
    artist = plain(f["meta"].get("Artist", ""))
    m = re.match(r"The original uploader was (.+?) at (.+?)\.?$", artist)
    if m:
        return f"{m.group(1)} ({m.group(2)})"
    if artist and "No machine-readable author" not in artist:
        return artist
    page = api(COMMONS_API, action="query", titles=f["title"], prop="revisions",
               rvprop="user", rvdir="newer", rvlimit=1)["query"]["pages"][0]
    return page["revisions"][0]["user"]


def sample_of(f: dict) -> str:
    """What the recording says, e.g. '[θa aθa]', if the description gives it."""
    found = re.findall(r"\{\{IPA\|(\[[^\]]+\])\}\}", f["wikitext"])
    return found[-1] if found else ""


# -------------------------------------------------------------------- audio
def decode(path: Path) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(RATE),
         "-af", "highpass=f=60", "-f", "f32le", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def clean(x: np.ndarray) -> np.ndarray:
    frame = int(RATE * 0.01)
    n = len(x) // frame
    rms = np.sqrt(np.mean(x[: n * frame].reshape(n, frame) ** 2, axis=1) + 1e-12)
    loud = np.flatnonzero(20 * np.log10(rms / rms.max()) > TRIM_DB)
    keep = int(RATE * KEEP_SECONDS)
    x = x[max(0, loud[0] * frame - keep) : min(len(x), (loud[-1] + 1) * frame + keep)]
    voiced = rms[loud[0] : loud[-1] + 1]
    level = float(np.sqrt(np.mean(voiced[voiced > rms.max() * 10 ** (TRIM_DB / 20)] ** 2)))
    gain = 10 ** (TARGET_RMS_DB / 20) / level
    gain = min(gain, 10 ** (PEAK_DB / 20) / float(np.abs(x).max()))
    x = x * gain
    fade = int(RATE * FADE_SECONDS)
    ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
    x[:fade] *= ramp
    x[-fade:] *= ramp[::-1]
    return x


def encode(x: np.ndarray, dest: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(RATE), "-ac", "1", "-i", "-",
         "-c:a", "libopus", "-b:a", "64k", "-map_metadata", "-1", str(dest)],
        input=x.astype(np.float32).tobytes(), check=True,
    )


def download(url: str, dest: Path) -> None:
    dest.write_bytes(fetch_url(url))


def slug(filename: str) -> str:
    stem = Path(filename).stem.lower()
    return re.sub(r"[^a-z0-9]+", "-", stem).strip("-")


# --------------------------------------------------------------------- main
def fetch(symbol: str, article: str, prefer: str | None, expect: str, tmp: Path, force: bool) -> dict:
    title, files = infobox_audio(article)
    if not files:
        raise SystemExit(f"/{symbol}/: {title} embeds no audio")
    norm = {f.replace(" ", "_"): f for f in files}
    if prefer is not None and prefer.replace(" ", "_") not in norm:
        raise SystemExit(f"/{symbol}/: {title} does not embed {prefer} (it has {files})")
    name = prefer or files[0]
    f = commons_file(name)
    license_name = plain(f["meta"].get("LicenseShortName", ""))
    if not FREE_LICENSE.match(license_name):
        raise SystemExit(f"/{symbol}/: {name} has a non-free license: {license_name!r}")
    described = plain(f["meta"].get("ImageDescription", "")) + " " + f["wikitext"]
    if not any(alt in described for alt in expect.split("|")):
        raise SystemExit(f"/{symbol}/: the description of {name} does not mention {expect!r}")

    out_name = slug(name) + ".ogg"
    out = OUT_DIR / out_name
    if out.exists() and not force:  # converted earlier: only refresh the metadata
        samples = len(decode(out))
    else:
        raw = tmp / ("src" + Path(name).suffix.lower())
        download(f["info"]["url"], raw)
        audio = clean(decode(raw))
        encode(audio, out)
        samples = len(audio)
        time.sleep(DOWNLOAD_PAUSE)
    entry = {
        "file": out_name,
        "duration": round(samples / RATE, 2),
        "title": f["title"],
        "source_url": f["info"]["descriptionurl"],
        "original_url": f["info"]["url"],
        "article": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
        "author": author_of(f),
        "license": license_name,
        "license_url": f["meta"].get("LicenseUrl", ""),
        "sample": sample_of(f),
    }
    print(f"/{symbol}/  {out_name:44} {entry['duration']:4.2f}s  {license_name:14} {entry['author']}")
    return entry


def write_markdown(entries: dict[str, dict]) -> None:
    lines = [
        "# Phoneme recordings: attribution",
        "",
        "Human recordings of IPA sounds from [Wikimedia Commons](https://commons.wikimedia.org/),",
        "as embedded in the infobox of each sound's English Wikipedia article. Generated by",
        "`scripts/fetch_phoneme_audio.py`.",
        "",
        "Changes: converted to mono 48 kHz Ogg/Opus, high-pass filtered at 60 Hz, leading and",
        "trailing silence trimmed, loudness-normalized. The modified files keep the license of",
        "their source (CC BY-SA files are shared under the same CC BY-SA version).",
        "",
        "| Sound | File | Says | Author | License |",
        "| --- | --- | --- | --- | --- |",
    ]
    for symbol, e in entries.items():
        lic = f"[{e['license']}]({e['license_url']})" if e["license_url"] else e["license"]
        lines.append(f"| /{symbol}/ | [{e['title']}]({e['source_url']}) → `{e['file']}` | "
                     f"{e['sample'] or '–'} | {e['author']} | {lic} |")
    (OUT_DIR / "ATTRIBUTION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_manifest(entries: dict[str, dict]) -> None:
    entries = {s: entries[s] for s in SOURCES if s in entries}
    (OUT_DIR / "attribution.json").write_text(json.dumps({
        "source": "Wikimedia Commons (IPA infobox audio of English Wikipedia articles)",
        "changes": "mono 48 kHz Ogg/Opus, 60 Hz high-pass, silence trimmed, loudness-normalized",
        "recordings": entries,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(entries)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("symbols", nargs="*", help="only these symbols (default: all)")
    parser.add_argument("--force", action="store_true",
                        help="download and convert again even if the .ogg already exists")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = OUT_DIR / "attribution.json"
    entries = json.loads(manifest.read_text("utf-8"))["recordings"] if manifest.exists() else {}
    wanted = args.symbols or list(SOURCES)
    with tempfile.TemporaryDirectory(prefix="pc-commons-") as tmp:
        for symbol in wanted:
            entries[symbol] = fetch(symbol, *SOURCES[symbol], Path(tmp), args.force)
            write_manifest(entries)  # progress survives a rate-limit failure; rerun to resume
            time.sleep(0.5)
    if not args.symbols:
        entries = {s: e for s, e in entries.items() if s in SOURCES}
        used = {e["file"] for e in entries.values()}
        for stale in OUT_DIR.glob("*.ogg"):
            if stale.name not in used:
                stale.unlink()
        write_manifest(entries)
    print(f"{len(entries)} recordings in {OUT_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
