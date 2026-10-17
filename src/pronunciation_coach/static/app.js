"use strict";

const $ = (id) => document.getElementById(id);
const SESSION_ID = (crypto.randomUUID && crypto.randomUUID()) || String(Date.now());

const state = {
  bookId: null,
  current: null,     // sentence payload from the API
  result: null,      // last score result
  recorder: null,
  chunks: [],
  busy: false,
};

// ------------------------------------------------------------------ helpers
async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch (_) { /* ignore */ }
    throw new Error(msg);
  }
  return res.json();
}

function setStatus(text) { $("status").textContent = text || ""; }

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children) node.append(c instanceof Node ? c : document.createTextNode(c ?? ""));
  return node;
}

function pct(x) { return x == null ? "–" : `${Math.round(x * 100)}%`; }
function statusOf(x) { return x >= 0.8 ? "good" : x >= 0.5 ? "unsure" : "bad"; }

// --------------------------------------------------------------------- tabs
function showTab(name) {
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${name}`));
  if (name === "library") loadBooks();
  if (name === "stats") loadStats();
  if (name === "sounds") renderSounds();
  if (name === "writing") renderWriting();
  closePopover();
}
document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
document.querySelectorAll("[data-goto]").forEach((a) =>
  a.addEventListener("click", (e) => { e.preventDefault(); showTab(a.dataset.goto); }));

// ------------------------------------------------------------------- speech
// Audio comes from the server: /api/tts (Piper, falling back to espeak-ng) for text and
// /api/tts/phoneme for isolated sounds (human recording, else the example word with Piper,
// else espeak-ng).
let player = null;
let playerUrl = null;
let speakAbort = null;
function stopSpeaking() {
  if (speakAbort) speakAbort.abort();
  speakAbort = null;
  if (player) player.pause();
  if (playerUrl) URL.revokeObjectURL(playerUrl);
  player = playerUrl = null;
  document.querySelectorAll(".ph.playing").forEach((n) => n.classList.remove("playing"));
}

const ttsUrl = (text, rate) => `/api/tts?${new URLSearchParams({ text, rate: String(rate) })}`;
const phonemeUrl = (symbol) => `/api/tts/phoneme?${new URLSearchParams({ symbol })}`;

// Fetch and play one clip; resolves when playback ends (or is stopped).
async function playClip(url, ctrl) {
  const res = await fetch(url, { signal: ctrl.signal });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  const blob = await res.blob();
  if (ctrl.signal.aborted) return;
  if (playerUrl) URL.revokeObjectURL(playerUrl);
  playerUrl = URL.createObjectURL(blob);
  player = new Audio(playerUrl);
  const audio = player;
  await new Promise((resolve, reject) => {
    audio.onended = resolve;
    audio.onerror = () => reject(new Error("could not play audio"));
    ctrl.signal.addEventListener("abort", resolve, { once: true });
    audio.play().catch(reject);
  });
}

// Play clips one after another. Each item: { url, before?, after? } (callbacks for highlighting).
async function playSequence(items, gapMs = 250) {
  stopSpeaking();
  const ctrl = new AbortController();
  speakAbort = ctrl;
  try {
    for (const [i, item] of items.entries()) {
      if (ctrl.signal.aborted) return;
      if (i && gapMs) await new Promise((r) => setTimeout(r, gapMs));
      item.before && item.before();
      try { await playClip(item.url, ctrl); } finally { item.after && item.after(); }
    }
  } catch (err) {
    if (err.name !== "AbortError" && speakAbort === ctrl) setStatus(`Speech error: ${err.message}`);
  }
}

function speak(text, rate = 0.9) { return playSequence([{ url: ttsUrl(text, rate) }]); }
function playPhoneme(symbol, chip) {
  return playSequence([{
    url: phonemeUrl(canon(symbol)),
    before: () => chip && chip.classList.add("playing"),
    after: () => chip && chip.classList.remove("playing"),
  }]);
}

// --------------------------------------------------------------- phoneme guide
const guide = { list: [], bySymbol: new Map(), aliases: {}, categories: [], loading: null };

function loadGuide() {
  if (!guide.loading) {
    guide.loading = api("/api/phonemes").then((data) => {
      guide.list = data.phonemes;
      guide.categories = data.categories;
      guide.aliases = data.aliases;
      for (const p of data.phonemes) guide.bySymbol.set(p.symbol, p);
    }).catch((err) => { guide.loading = null; throw err; });
  }
  return guide.loading;
}

function canon(symbol) { return guide.aliases[symbol] || symbol; }
function entryFor(symbol) { return guide.bySymbol.get(canon(symbol)) || null; }

const SVG_NS = "http://www.w3.org/2000/svg";
function playIcon() {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("class", "icon");
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", "M5 3.2v9.6a.6.6 0 0 0 .9.5l7.4-4.8a.6.6 0 0 0 0-1L5.9 2.7a.6.6 0 0 0-.9.5z");
  svg.append(path);
  return svg;
}

// A clickable phoneme: plays the sound and opens the short guide.
function phChip(symbol) {
  const entry = entryFor(symbol);
  if (!entry) {
    return el("span", { class: "ph unknown", title: "Not part of the American English sounds in the guide" },
      `/${symbol}/`);
  }
  const chip = el("button", {
    class: `ph${entry.hard ? " hard" : ""}`, type: "button", "data-symbol": entry.symbol,
    title: `${entry.name}: click to hear it`,
  }, `/${entry.symbol}/`);
  chip.addEventListener("click", (e) => {
    e.stopPropagation();
    playPhoneme(entry.symbol, chip);
    openPopover(entry, chip);
  });
  return chip;
}

function phList(tokens) {
  const box = el("span", { class: "ph-list" });
  if (!tokens.length) box.append(el("span", { class: "muted" }, "—"));
  for (const t of tokens) box.append(phChip(t));
  return box;
}

function exampleWord(ex, cls = "ex") {
  const btn = el("button", { class: cls, type: "button", title: `Hear "${ex.word}"` });
  for (const part of ex.parts) btn.append(part.focus ? el("mark", {}, part.text) : part.text);
  btn.addEventListener("click", (e) => { e.stopPropagation(); speak(ex.word, 0.75); });
  return btn;
}

// ---------------------------------------------------------------- popover
let popAnchor = null;
function closePopover() {
  $("ph-pop").classList.add("hidden");
  popAnchor = null;
}

function openPopover(entry, anchor) {
  const pop = $("ph-pop");
  const firstEx = entry.examples[0];
  pop.replaceChildren(
    el("div", { class: "pop-head" },
      el("button", {
        class: "pop-symbol", type: "button", title: "Hear the sound",
        onclick: () => playPhoneme(entry.symbol),
      }, playIcon(), `/${entry.symbol}/`),
      el("div", {},
        el("div", { class: "pop-name" }, entry.name),
        entry.hard ? el("span", { class: "badge" }, "Hard for Spanish speakers") : ""),
      el("button", { class: "pop-close", type: "button", "aria-label": "Close", onclick: closePopover }, "×")),
    el("p", { class: "pop-how", lang: "es" }, entry.tip),
    el("p", { class: "pop-es", lang: "es" }, entry.spanish),
    firstEx ? el("div", { class: "pop-ex" }, "Example: ", exampleWord(firstEx)) : "",
    el("a", {
      href: "#", class: "pop-link",
      onclick: (e) => { e.preventDefault(); goToSound(entry.symbol); },
    }, "Open in Sounds →"),
  );
  pop.classList.remove("hidden");
  popAnchor = anchor;
  positionPopover();
}

function positionPopover() {
  const pop = $("ph-pop");
  if (!popAnchor || pop.classList.contains("hidden")) return;
  if (window.matchMedia("(max-width: 600px)").matches) {  // bottom sheet on phones (CSS)
    pop.style.left = pop.style.top = "";
    return;
  }
  const r = popAnchor.getBoundingClientRect();
  const w = pop.offsetWidth, h = pop.offsetHeight, m = 12;
  let left = Math.min(Math.max(m, r.left + r.width / 2 - w / 2), window.innerWidth - w - m);
  let top = r.bottom + 8;
  if (top + h > window.innerHeight - m) top = Math.max(m, r.top - h - 8);
  pop.style.left = `${left}px`;
  pop.style.top = `${top}px`;
}
window.addEventListener("resize", positionPopover);
window.addEventListener("scroll", () => popAnchor && closePopover(), { passive: true });
document.addEventListener("click", (e) => {
  if (popAnchor && !$("ph-pop").contains(e.target)) closePopover();
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePopover(); });

async function goToSound(symbol) {
  closePopover();
  if (hardOnly() && entryFor(symbol) && !entryFor(symbol).hard) setHardOnly(false);
  showTab("sounds");
  await renderSounds();
  const card = document.querySelector(`.sound-card[data-symbol="${CSS.escape(canon(symbol))}"]`);
  if (!card) return;
  card.scrollIntoView({ behavior: "smooth", block: "center" });
  card.classList.remove("flash");
  void card.offsetWidth;
  card.classList.add("flash");
}

// ---------------------------------------------------------------- sounds tab
const SOURCE_LABEL = {
  recording: "Human recording",
  piper: "Heard in a word",
  espeak: "Synthesized",
};

let soundFilter = "all";  // "all" | "hard"
try { if (localStorage.getItem("pc.hardOnly") === "1") soundFilter = "hard"; } catch {}
function hardOnly() { return soundFilter === "hard"; }
function setHardOnly(v) {
  soundFilter = v ? "hard" : "all";
  try { localStorage.setItem("pc.hardOnly", v ? "1" : "0"); } catch {}
  document.querySelectorAll("#sound-filter [data-filter]").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.filter === soundFilter)));
}
document.querySelectorAll("#sound-filter [data-filter]").forEach((b) =>
  b.addEventListener("click", () => { setHardOnly(b.dataset.filter === "hard"); renderSounds(); }));
setHardOnly(hardOnly());

function speakerIcon() {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("class", "icon");
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", "M2.5 6h2l3-2.6a.4.4 0 0 1 .7.3v8.6a.4.4 0 0 1-.7.3L4.5 10h-2a.5.5 0 0 1-.5-.5v-3a.5.5 0 0 1 .5-.5zM10.6 5.2a.6.6 0 0 1 .85.05 4.1 4.1 0 0 1 0 5.5.6.6 0 1 1-.9-.8 2.9 2.9 0 0 0 0-3.9.6.6 0 0 1 .05-.85z");
  svg.append(path);
  return svg;
}

function wordButton(ex, rate = 0.75) {
  const btn = el("button", { class: "word", type: "button", title: `Hear "${ex.word}"` }, speakerIcon());
  const text = el("span", {});
  for (const part of ex.parts) text.append(part.focus ? el("mark", {}, part.text) : part.text);
  btn.append(text);
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    playSequence([{ url: ttsUrl(ex.word, rate), before: () => btn.classList.add("playing"),
                    after: () => btn.classList.remove("playing") }]);
  });
  return btn;
}

function sourceNote(p) {
  if (p.source === "recording") {
    return el("span", { class: "source" }, SOURCE_LABEL.recording,
      p.recording.sample ? el("span", { class: "sample" }, ` · says ${p.recording.sample}`) : "");
  }
  if (p.source === "piper" && p.listen_word) {
    return el("span", { class: "source" }, `${SOURCE_LABEL.piper}: `, el("i", {}, p.listen_word));
  }
  return el("span", { class: "source" }, SOURCE_LABEL[p.source] || "");
}

function soundCard(p) {
  const card = el("article", {
    class: `sound-card${p.hard ? " is-hard" : ""}`, "data-symbol": p.symbol, id: `sound-${p.symbol}`,
    "aria-labelledby": `sound-name-${p.symbol}`,
  });
  const play = el("button", {
    class: "sound-play", type: "button", "aria-label": `Play /${p.symbol}/, ${p.name}`,
  }, el("span", { class: "sound-glyph" }, p.symbol), el("span", { class: "sound-play-hint" }, playIcon(), "Play"));
  play.addEventListener("click", () => playPhoneme(p.symbol, play));

  card.append(el("header", { class: "sound-head" },
    play,
    el("div", { class: "sound-title" },
      el("h3", { id: `sound-name-${p.symbol}` }, p.name),
      el("p", { class: "sound-meta" },
        p.hard ? el("span", { class: "hard-flag" }, "Hard for Spanish speakers") : "",
        sourceNote(p)))));

  const body = el("div", { class: "sound-body" },
    el("p", { class: "sound-how", lang: "es" }, p.how),
    el("p", { class: "sound-es", lang: "es" }, el("span", { class: "label" }, "Spanish"), p.spanish));
  card.append(body);

  if (p.examples.length) {
    card.append(el("div", { class: "sound-row" },
      el("span", { class: "label" }, "Examples"),
      el("div", { class: "words" }, ...p.examples.map((ex) => wordButton(ex)))));
  }

  if (p.pair) {
    const [a, b] = p.pair.words;
    const wa = wordButton({ word: a, parts: [{ text: a, focus: false }] });
    const wb = wordButton({ word: b, parts: [{ text: b, focus: false }] });
    const both = el("button", { class: "ghost play small", type: "button", title: `Hear "${a}" then "${b}"` },
      playIcon(), "Both");
    both.addEventListener("click", () => playSequence([
      { url: ttsUrl(a, 0.75), before: () => wa.classList.add("playing"), after: () => wa.classList.remove("playing") },
      { url: ttsUrl(b, 0.75), before: () => wb.classList.add("playing"), after: () => wb.classList.remove("playing") },
    ], 500));
    card.append(el("div", { class: "sound-pair" },
      el("div", { class: "pair-head" },
        el("span", { class: "label" }, "Minimal pair"),
        p.pair.contrast ? el("span", { class: "pair-contrast" }, phChip(p.symbol), "vs", phChip(p.pair.contrast)) : ""),
      el("div", { class: "pair-words" }, wa, el("span", { class: "vs" }, "vs"), wb, both),
      p.pair.note ? el("p", { class: "pair-note", lang: "es" }, p.pair.note) : ""));
  }

  if (p.recording) {
    const r = p.recording;
    card.append(el("p", { class: "credit" },
      "Recording: ",
      el("a", { href: r.source_url, target: "_blank", rel: "noopener" }, r.author),
      ", ",
      r.license_url ? el("a", { href: r.license_url, target: "_blank", rel: "noopener" }, r.license) : r.license,
      ", via Wikimedia Commons"));
  }
  return card;
}

function renderCredits() {
  const recs = guide.list.filter((p) => p.recording);
  const licenses = [...new Set(recs.map((p) => p.recording.license))].sort();
  $("sound-credits-summary").textContent =
    `Audio credits: ${recs.length} human recordings from Wikimedia Commons (${licenses.join(", ")})`;
  $("sound-credits-list").replaceChildren(...recs.map((p) => el("li", {},
    el("span", { class: "credit-sym" }, `/${p.symbol}/`),
    el("a", { href: p.recording.source_url, target: "_blank", rel: "noopener" }, p.recording.title.replace(/^File:/, "")),
    ` by ${p.recording.author}, ${p.recording.license}`)));
}

async function renderSounds() {
  try { await loadGuide(); } catch (err) { setStatus(`Error: ${err.message}`); return; }
  const only = hardOnly();
  const box = $("sounds");
  const index = $("sound-index");
  const nHard = guide.list.filter((p) => p.hard).length;
  $("count-all").textContent = guide.list.length;
  $("count-hard").textContent = nHard;
  box.replaceChildren();
  index.replaceChildren();
  for (const cat of guide.categories) {
    const items = guide.list.filter((p) => p.category === cat.id && (!only || p.hard));
    if (!items.length) continue;
    box.append(el("section", { class: "sound-group", id: `sounds-${cat.id}`, "aria-labelledby": `sounds-h-${cat.id}` },
      el("h2", { class: "group-title", id: `sounds-h-${cat.id}` }, cat.title,
        el("span", { class: "group-count" }, String(items.length))),
      el("div", { class: "sound-grid" }, ...items.map(soundCard))));
    index.append(el("div", { class: "index-group" },
      el("span", { class: "index-title" }, cat.title),
      el("div", { class: "index-tiles" }, ...items.map((p) => el("a", {
        href: `#sound-${p.symbol}`, class: `index-tile${p.hard ? " is-hard" : ""}`,
        title: p.name + (p.hard ? " (hard for Spanish speakers)" : ""),
        onclick: (e) => { e.preventDefault(); goToSound(p.symbol); },
      }, p.symbol)))));
  }
  renderCredits();
}

// ------------------------------------------------------------------ practice
function renderSentence() {
  const s = state.current;
  const box = $("sentence");
  box.replaceChildren();
  const words = state.result ? state.result.words : null;
  for (const seg of s.segments) {
    if (seg.word == null) { box.append(seg.text); continue; }
    const w = words && words[seg.word];
    const span = el("span", { class: `w ${w ? w.status : ""}`, "data-word": seg.word }, seg.text);
    if (w && w.score != null) span.title = `${pct(w.score)} — /${w.expected.join(" ")}/`;
    span.addEventListener("click", () => selectWord(seg.word, seg.text));
    box.append(span);
  }
  $("book-title").textContent = s.title;
  $("progress").textContent = `Sentence ${s.idx + 1} of ${s.total}`;
  $("prev").disabled = s.idx <= 0;
  $("next").disabled = s.idx >= s.total - 1;
}

function selectWord(index, text) {
  speak(text, 0.8);
  document.querySelectorAll(".w.selected").forEach((n) => n.classList.remove("selected"));
  const node = document.querySelector(`.w[data-word="${index}"]`);
  if (node) node.classList.add("selected");
  if (!state.result) return;
  const w = state.result.words[index];
  const d = $("word-detail");
  const expected = phList(w.expected);
  const steps = w.expected.filter((t) => entryFor(t)).length;
  d.replaceChildren(
    el("div", {}, el("b", {}, w.text), ` · ${pct(w.score)}`),
    el("div", { class: "detail-row" }, el("span", { class: "label" }, "Expected"), expected),
    el("div", { class: "detail-row" }, el("span", { class: "label" }, "Heard"), phList(w.heard)),
    steps ? el("button", {
      class: "ghost play small", type: "button", title: "Hear each expected sound, one at a time",
      onclick: () => playSequence([...expected.querySelectorAll("button.ph")].map((chip) => ({
        url: phonemeUrl(chip.dataset.symbol),
        before: () => chip.classList.add("playing"),
        after: () => chip.classList.remove("playing"),
      })).concat([{ url: ttsUrl(w.text, 0.75) }]), 300),
    }, playIcon(), "Sound by sound") : "",
  );
}

function renderResult() {
  const r = state.result;
  $("result").classList.toggle("hidden", !r);
  if (!r) return;
  const sc = $("score");
  sc.className = `score ${statusOf(r.accuracy)}`;
  sc.replaceChildren(el("small", {}, "Accuracy"), pct(r.accuracy));
  $("word-detail").replaceChildren(el("div", {}, "Click a word to compare its sounds."));
  const list = $("errors");
  list.replaceChildren();
  const errs = r.errors.filter((e) => e.kind !== "close");
  const close = r.errors.filter((e) => e.kind === "close");
  if (!errs.length) list.append(el("li", {}, el("span", { class: "msg" }, "No clear errors. Nice!")));
  for (const e of [...errs, ...close]) {
    list.append(el("li", {},
      el("div", { class: "msg" }, errorMessage(e), e.kind === "close" ? el("span", { class: "muted" }, " (close)") : ""),
      e.tip ? el("div", { class: "tip", lang: "es" }, e.tip) : ""));
  }
  $("raw-expected").replaceChildren(phList(r.expected));
  $("raw-heard").replaceChildren(phList(r.recognized));
  $("raw-device").textContent = r.device
    ? `Recognized on ${r.device} (${r.device_name}) in ${r.infer_seconds?.toFixed(2)} s` : "";
}

// "think: said /t/, expected /θ/" with clickable sounds (same wording as the server's message).
function errorMessage(e) {
  const frag = document.createDocumentFragment();
  frag.append(`${e.word}: `);
  if (e.kind === "substitution" || e.kind === "close") {
    frag.append("said ", phChip(e.actual), ", expected ", phChip(e.expected));
  } else if (e.kind === "deletion") {
    frag.append("missing ", phChip(e.expected));
  } else {
    frag.append("extra ", phChip(e.actual));
  }
  return frag;
}

async function loadSentence(idx) {
  if (state.bookId == null) return;
  const q = idx == null ? "" : `?idx=${idx}`;
  state.current = await api(`/api/books/${state.bookId}/sentence${q}`);
  state.result = null;
  renderSentence();
  renderResult();
}

async function openBook(id) {
  state.bookId = id;
  $("no-book").classList.add("hidden");
  $("practice").classList.remove("hidden");
  await loadSentence(null);
  showTab("practice");
}

$("prev").addEventListener("click", () => state.current && loadSentence(state.current.idx - 1));
$("next").addEventListener("click", () => state.current && loadSentence(state.current.idx + 1));
$("retry").addEventListener("click", () => { state.result = null; renderSentence(); renderResult(); });
$("listen").addEventListener("click", () => state.current && speak(state.current.text));

// ------------------------------------------------------------------ recording
function pickMime() {
  const types = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
  return types.find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || "";
}

async function startRecording() {
  if (state.busy || !state.current) return;
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
  } catch (err) {
    setStatus(`Microphone error: ${err.message}`);
    return;
  }
  const mimeType = pickMime();
  const rec = new MediaRecorder(stream, mimeType ? { mimeType } : {});
  state.chunks = [];
  rec.ondataavailable = (e) => e.data.size && state.chunks.push(e.data);
  rec.onstop = () => {
    stream.getTracks().forEach((t) => t.stop());
    submitRecording(new Blob(state.chunks, { type: rec.mimeType || "audio/webm" }));
  };
  rec.start();
  state.recorder = rec;
  $("record").classList.add("recording");
  $("record-label").textContent = "Stop";
  setStatus("Recording… read the sentence aloud");
}

function stopRecording() {
  if (state.recorder && state.recorder.state === "recording") state.recorder.stop();
  state.recorder = null;
  $("record").classList.remove("recording");
  $("record-label").textContent = "Record";
}

async function submitRecording(blob) {
  state.busy = true;
  $("record").disabled = true;
  $("record-label").textContent = "Scoring…";
  setStatus("Scoring (the first attempt loads the model, this can take a while)…");
  try {
    const form = new FormData();
    form.append("audio", blob, "attempt.webm");
    form.append("text", state.current.text);
    form.append("book_id", state.current.book_id);
    form.append("sentence_idx", state.current.idx);
    form.append("session_id", SESSION_ID);
    state.result = await api("/api/score", { method: "POST", body: form });
    renderSentence();
    renderResult();
    setStatus("");
  } catch (err) {
    setStatus(`Error: ${err.message}`);
  } finally {
    state.busy = false;
    $("record").disabled = false;
    $("record-label").textContent = "Record";
  }
}

function toggleRecording() {
  if (state.recorder) stopRecording(); else startRecording();
}
$("record").addEventListener("click", toggleRecording);

document.addEventListener("keydown", (e) => {
  const tag = (e.target.tagName || "").toLowerCase();
  if (tag === "input" || tag === "textarea" || e.target.isContentEditable) return;
  if (!$("tab-practice").classList.contains("active")) return;
  if (e.code === "Space") { e.preventDefault(); if (!e.repeat) toggleRecording(); }
  else if (e.key === "ArrowRight" && !state.recorder) $("next").click();
  else if (e.key === "ArrowLeft" && !state.recorder) $("prev").click();
});

// -------------------------------------------------------------------- library
async function loadBooks() {
  const { books } = await api("/api/books");
  const list = $("books");
  list.replaceChildren();
  if (!books.length) list.append(el("li", { class: "muted" }, "No books yet."));
  for (const b of books) {
    const progress = b.sentence_count ? (b.position + 1) / b.sentence_count : 0;
    list.append(el("li", {},
      el("span", { class: "title", title: b.title }, b.title),
      el("span", { class: "meta" }, `${b.position + 1} / ${b.sentence_count}`),
      el("span", { class: "bar" }, Object.assign(el("span"), { style: `width:${progress * 100}%` })),
      el("button", { class: "primary", onclick: () => openBook(b.id) }, "Read"),
      el("button", {
        class: "ghost", title: "Delete book",
        onclick: async () => {
          if (!confirm(`Delete "${b.title}"? Attempt history is kept.`)) return;
          await api(`/api/books/${b.id}`, { method: "DELETE" });
          if (state.bookId === b.id) { state.bookId = null; state.current = null; init(); }
          loadBooks();
        },
      }, "Delete"),
    ));
  }
}

$("upload").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData();
  const file = $("file").files[0];
  const text = $("paste").value.trim();
  if (file) form.append("file", file);
  else if (text) form.append("text", text);
  else return setStatus("Choose a file or paste some text");
  setStatus("Importing…");
  try {
    const book = await api("/api/books", { method: "POST", body: form });
    setStatus(`Added "${book.title}" (${book.sentence_count} sentences)`);
    $("file").value = "";
    $("paste").value = "";
    loadBooks();
  } catch (err) {
    setStatus(`Error: ${err.message}`);
  }
});

// ---------------------------------------------------------------------- stats
function renderChart(days) {
  const box = $("chart");
  if (!days.length) { box.textContent = "No attempts yet."; return; }
  const W = 600, H = 220, P = { l: 36, r: 12, t: 12, b: 28 };
  const x = (i) => P.l + (days.length === 1 ? (W - P.l - P.r) / 2 : (i * (W - P.l - P.r)) / (days.length - 1));
  const y = (v) => P.t + (1 - v) * (H - P.t - P.b);
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("preserveAspectRatio", "none");
  const add = (tag, attrs, text) => {
    const n = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (text != null) n.textContent = text;
    svg.append(n);
    return n;
  };
  for (const v of [0, 0.5, 0.8, 1]) {
    add("line", { x1: P.l, x2: W - P.r, y1: y(v), y2: y(v), class: "axis" });
    add("text", { x: 4, y: y(v) + 4 }, `${v * 100}%`);
  }
  add("polyline", { class: "line", points: days.map((d, i) => `${x(i)},${y(d.avg_accuracy)}`).join(" ") });
  days.forEach((d, i) => {
    add("circle", { cx: x(i), cy: y(d.avg_accuracy), r: 3.5, class: "pt" })
      .append(Object.assign(document.createElementNS(ns, "title"),
        { textContent: `${d.day}: ${pct(d.avg_accuracy)} (${d.attempts} attempts)` }));
  });
  const step = Math.max(1, Math.ceil(days.length / 6));
  days.forEach((d, i) => { if (i % step === 0) add("text", { x: x(i) - 16, y: H - 8 }, d.day.slice(5)); });
  box.replaceChildren(svg);
}

async function loadStats() {
  await loadGuide().catch(() => {});
  const s = await api("/api/stats");
  const recent = s.recent.slice(-10);
  const recentAvg = recent.length ? recent.reduce((a, r) => a + r.accuracy, 0) / recent.length : null;
  const today = s.by_day.length ? s.by_day[s.by_day.length - 1] : null;
  $("kpis").replaceChildren(
    ...[
      ["Attempts", s.overall.attempts],
      ["Average", pct(s.overall.avg_accuracy)],
      ["Last 10 attempts", pct(recentAvg)],
      [today ? `Latest day (${today.day})` : "Latest day", pct(today && today.avg_accuracy)],
    ].map(([l, v]) => el("div", { class: "kpi" }, el("div", { class: "v" }, String(v ?? "–")), el("div", { class: "l" }, l))),
  );
  renderChart(s.by_day);
  renderStatsWriting();

  const top = $("top-errors");
  top.replaceChildren();
  if (!s.top_errors.length) top.append(el("li", { class: "muted" }, "No errors recorded yet."));
  for (const e of s.top_errors) {
    const label = el("span", {});
    if (e.kind === "substitution") label.append(phChip(e.expected), " → ", phChip(e.actual));
    else if (e.kind === "deletion") label.append("missing ", phChip(e.expected));
    else label.append("extra ", phChip(e.actual));
    const words = (e.words || "").split(",").slice(0, 5).join(", ");
    top.append(el("li", {},
      el("span", { class: "count" }, `×${e.count}`),
      el("div", { class: "msg" }, label),
      el("div", { class: "tip" }, `e.g. ${words}`),
      e.tip ? el("div", { class: "tip", lang: "es" }, e.tip) : ""));
  }

  const table = $("sessions");
  table.replaceChildren(el("tr", {}, el("th", {}, "Started"), el("th", {}, "Attempts"), el("th", {}, "Average")));
  for (const r of s.by_session) {
    table.append(el("tr", {},
      el("td", {}, new Date(r.started_at).toLocaleString()),
      el("td", { class: "num" }, String(r.attempts)),
      el("td", { class: "num" }, pct(r.avg_accuracy))));
  }
}

// ----------------------------------------------------------------------- init
async function init() {
  loadGuide().then(() => state.result && (renderResult(), renderSentence())).catch(() => {});
  try {
    const health = await api("/api/health");
    if (!health.espeak) setStatus("espeak-ng is not installed: scoring is unavailable");
    const { last_book_id } = await api("/api/books");
    if (last_book_id != null) await openBook(last_book_id);
    else {
      $("no-book").classList.remove("hidden");
      $("practice").classList.add("hidden");
    }
  } catch (err) {
    setStatus(`Error: ${err.message}`);
  }
  const tab = location.hash.slice(1);
  if (document.querySelector(`.tab[data-tab="${CSS.escape(tab)}"]`)) showTab(tab);
}
init();
