"""Book text extraction (EPUB, PDF, TXT), sentence splitting and chapter/page structure."""

from __future__ import annotations

import io
import posixpath
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

MAX_WORDS = 40
SENTENCES_PER_PAGE = 15

_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", " ": " ", "­": ""})
_BLOCK_TAGS = ["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote",
               "pre", "dd", "dt", "tr", "section", "article", "figcaption", "title"]


_NUMBER_WORDS = ("one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen"
                 "|fifteen|sixteen|seventeen|eighteen|nineteen")
_TENS = "twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety"
_HEADING_RE = re.compile(
    rf"(?:chapter|part)\s+(?:\d+|[ivxlcdm]+|(?:{_TENS})(?:[- ](?:{_NUMBER_WORDS}))?|{_NUMBER_WORDS})\b"
    r"(?:\s*[.:\-–—]\s*(?P<sep>.*)|\s+(?P<bare>[^.!?]*)|\s*)",
    re.IGNORECASE,
)


class UnsupportedFormat(ValueError):
    pass


@dataclass
class Paragraph:
    text: str
    chapter: str | None = None  # title of the chapter that starts at this paragraph
    page: int | None = None     # 0-based source page (PDF only)


@dataclass
class Extracted:
    title: str
    paragraphs: list[Paragraph]
    real_pages: bool = False

    @property
    def texts(self) -> list[str]:
        return [p.text for p in self.paragraphs]


@dataclass
class Layout:
    sentences: list[str]
    chapters: list[tuple[str, int]] = field(default_factory=list)  # (title, start sentence)
    page_starts: list[int] | None = None  # real pages only; None means virtual pages


def virtual_page_count(sentence_count: int) -> int:
    return max(1, -(-sentence_count // SENTENCES_PER_PAGE))


def _soup(html: bytes | str):
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    return soup


def _soup_paragraphs(soup) -> list[str]:
    for br in soup.find_all("br"):
        br.replace_with("\n\n")
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.append("\n\n")
    return split_paragraphs(soup.get_text(""))


def _html_to_paragraphs(html: bytes | str) -> list[str]:
    return _soup_paragraphs(_soup(html))


def is_chapter_heading(paragraph: str) -> bool:
    if len(paragraph) > 80:
        return False
    return _HEADING_RE.fullmatch(paragraph.strip()) is not None


def text_paragraphs(text: str) -> list[Paragraph]:
    return [Paragraph(p, chapter=p if is_chapter_heading(p) else None) for p in split_paragraphs(text)]


def split_paragraphs(text: str) -> list[str]:
    """Split on blank lines; single newlines inside a paragraph become spaces."""
    text = text.translate(_QUOTES).replace("\r\n", "\n")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # de-hyphenate line breaks
    paras = re.split(r"\n\s*\n", text)
    out = []
    for p in paras:
        p = re.sub(r"\s+", " ", p).strip()
        if p:
            out.append(p)
    return out


def _toc_titles(toc, names: dict[str, str]) -> dict[str, str]:
    """Map document names to the first TOC title that points at them (fragments ignored)."""
    out: dict[str, str] = {}

    def walk(entries):
        for entry in entries:
            node, children = entry if isinstance(entry, tuple) else (entry, [])
            href = unquote((getattr(node, "href", "") or "").split("#")[0])
            name = names.get(href) or names.get(posixpath.normpath(href)) or names.get(posixpath.basename(href))
            title = re.sub(r"\s+", " ", getattr(node, "title", "") or "").strip()
            if name and title and name not in out:
                out[name] = title
            walk(children)

    walk(toc)
    return out


def extract_epub(data: bytes, filename: str) -> Extracted:
    import ebooklib
    from ebooklib import epub

    with tempfile.NamedTemporaryFile(suffix=".epub") as tmp:
        tmp.write(data)
        tmp.flush()
        book = epub.read_epub(tmp.name, options={"ignore_ncx": True})
    titles = book.get_metadata("DC", "title")
    title = titles[0][0] if titles else Path(filename).stem
    seen = set()
    items = [book.get_item_with_id(idref) for idref, _ in book.spine]
    items += [i for i in book.get_items_of_type(ebooklib.ITEM_DOCUMENT) if i not in items]
    docs = []
    for item in items:
        if item is None or item.get_id() in seen or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        seen.add(item.get_id())
        if not isinstance(item, epub.EpubNav):  # the TOC page itself is not reading material
            docs.append(item)
    names = {}
    for item in docs:
        names.setdefault(item.get_name(), item.get_name())
        names.setdefault(posixpath.basename(item.get_name()), item.get_name())
    toc = _toc_titles(book.toc or [], names)
    paragraphs: list[Paragraph] = []
    for item in docs:
        soup = _soup(item.get_content())
        heading = soup.find(["h1", "h2", "h3"])
        heading = re.sub(r"\s+", " ", heading.get_text(" ")).strip() if heading else ""
        texts = _soup_paragraphs(soup)
        if not texts:
            continue
        if toc:
            chapter = toc.get(item.get_name())
        else:
            chapter = heading or f"Chapter {sum(p.chapter is not None for p in paragraphs) + 1}"
        paragraphs.append(Paragraph(texts[0], chapter=chapter))
        paragraphs.extend(Paragraph(t) for t in texts[1:])
    return Extracted(title, paragraphs)


def _outline_pages(reader) -> list[tuple[str, int]]:
    try:
        outline = reader.outline
    except Exception:
        return []
    top = [o for o in outline if not isinstance(o, list)]
    if len(top) <= 1:  # a single root (usually the book title): use its children
        nested = next((o for o in outline if isinstance(o, list)), None)
        if nested:
            top = [o for o in nested if not isinstance(o, list)]
    out = []
    for dest in top:
        try:
            page = reader.get_destination_page_number(dest)
        except Exception:
            continue
        title = re.sub(r"\s+", " ", str(getattr(dest, "title", "") or "")).strip()
        if page is not None and page >= 0 and title:
            out.append((title, page))
    return out


def extract_pdf(data: bytes, filename: str) -> Extracted:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    meta_title = (reader.metadata.title if reader.metadata else None) or ""
    title = meta_title.strip() or Path(filename).stem
    chapters: dict[int, str] = {}
    for name, page in _outline_pages(reader):
        chapters.setdefault(page, name)
    paragraphs: list[Paragraph] = []
    pending = None  # chapter whose page had no text yet
    for n, page in enumerate(reader.pages):
        pending = chapters.get(n, pending)
        for text in split_paragraphs(page.extract_text() or ""):
            paragraphs.append(Paragraph(text, chapter=pending, page=n))
            pending = None
    return Extracted(title, paragraphs, real_pages=True)


def extract_txt(data: bytes, filename: str) -> Extracted:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    return Extracted(Path(filename).stem, text_paragraphs(text))


def extract_book(filename: str, data: bytes) -> Extracted:
    ext = Path(filename).suffix.lower()
    if ext == ".epub":
        return extract_epub(data, filename)
    if ext == ".pdf":
        return extract_pdf(data, filename)
    if ext in (".txt", ".text", ".md", ""):
        return extract_txt(data, filename)
    raise UnsupportedFormat(f"unsupported file type: {ext}")


def extract(filename: str, data: bytes) -> tuple[str, list[str]]:
    book = extract_book(filename, data)
    return book.title, book.texts


_segmenter = None


def _seg():
    global _segmenter
    if _segmenter is None:
        import pysbd

        _segmenter = pysbd.Segmenter(language="en", clean=False)
    return _segmenter


def _split_long(sentence: str) -> list[str]:
    if len(sentence.split()) <= MAX_WORDS:
        return [sentence]
    parts = [p.strip() for p in re.split(r"(?<=[;:])\s+", sentence) if p.strip()]
    if len(parts) > 1:
        return [q for p in parts for q in _split_long(p)]
    words = sentence.split()
    return [" ".join(words[i : i + MAX_WORDS]) for i in range(0, len(words), MAX_WORDS)]


def _paragraph_sentences(para: str) -> list[str]:
    out: list[str] = []
    for s in _seg().segment(para):
        s = re.sub(r"\s+", " ", s).strip()
        if not re.search(r"[A-Za-z]", s):
            continue
        out.extend(_split_long(s))
    return out


def split_sentences(paragraphs: list[str] | str) -> list[str]:
    if isinstance(paragraphs, str):
        paragraphs = split_paragraphs(paragraphs)
    return [s for para in paragraphs for s in _paragraph_sentences(para)]


def layout(paragraphs: list[Paragraph], real_pages: bool = False) -> Layout:
    """Split into sentences, recording where each chapter and (real) page starts."""
    sentences: list[str] = []
    chapters: list[tuple[str, int]] = []
    page_first: dict[int, int] = {}
    for para in paragraphs:
        start = len(sentences)
        sentences.extend(_paragraph_sentences(para.text))
        if para.chapter:
            if chapters and chapters[-1][1] == start:
                chapters.pop()  # an empty chapter collapses into the next one
            chapters.append((para.chapter, start))
        if para.page is not None and len(sentences) > start:
            page_first.setdefault(para.page, start)
    chapters = [c for c in chapters if c[1] < len(sentences)]
    page_starts = None
    if real_pages and page_first:
        page_starts = [0] * (max(page_first) + 1)
        nxt = len(sentences) - 1
        for n in range(len(page_starts) - 1, -1, -1):  # blank pages point at the next text
            nxt = page_first.get(n, nxt)
            page_starts[n] = nxt
    return Layout(sentences, chapters, page_starts)
