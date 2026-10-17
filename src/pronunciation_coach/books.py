"""Book text extraction (EPUB, PDF, TXT) and sentence splitting."""

from __future__ import annotations

import io
import re
import tempfile
from pathlib import Path

MAX_WORDS = 40

_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", " ": " ", "­": ""})
_BLOCK_TAGS = ["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote",
               "pre", "dd", "dt", "tr", "section", "article", "figcaption", "title"]


class UnsupportedFormat(ValueError):
    pass


def _html_to_paragraphs(html: bytes | str) -> list[str]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n\n")
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.append("\n\n")
    return split_paragraphs(soup.get_text(""))


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


def extract_epub(data: bytes, filename: str) -> tuple[str, list[str]]:
    import ebooklib
    from ebooklib import epub

    with tempfile.NamedTemporaryFile(suffix=".epub") as tmp:
        tmp.write(data)
        tmp.flush()
        book = epub.read_epub(tmp.name, options={"ignore_ncx": True})
    titles = book.get_metadata("DC", "title")
    title = titles[0][0] if titles else Path(filename).stem
    paragraphs: list[str] = []
    seen = set()
    items = [book.get_item_with_id(idref) for idref, _ in book.spine]
    items += [i for i in book.get_items_of_type(ebooklib.ITEM_DOCUMENT) if i not in items]
    for item in items:
        if item is None or item.get_id() in seen or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        seen.add(item.get_id())
        paragraphs.extend(_html_to_paragraphs(item.get_content()))
    return title, paragraphs


def extract_pdf(data: bytes, filename: str) -> tuple[str, list[str]]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    meta_title = (reader.metadata.title if reader.metadata else None) or ""
    title = meta_title.strip() or Path(filename).stem
    pages = [(page.extract_text() or "") for page in reader.pages]
    return title, split_paragraphs("\n\n".join(pages))


def extract_txt(data: bytes, filename: str) -> tuple[str, list[str]]:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    return Path(filename).stem, split_paragraphs(text)


def extract(filename: str, data: bytes) -> tuple[str, list[str]]:
    ext = Path(filename).suffix.lower()
    if ext == ".epub":
        return extract_epub(data, filename)
    if ext == ".pdf":
        return extract_pdf(data, filename)
    if ext in (".txt", ".text", ".md", ""):
        return extract_txt(data, filename)
    raise UnsupportedFormat(f"unsupported file type: {ext}")


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


def split_sentences(paragraphs: list[str] | str) -> list[str]:
    if isinstance(paragraphs, str):
        paragraphs = split_paragraphs(paragraphs)
    out: list[str] = []
    for para in paragraphs:
        for s in _seg().segment(para):
            s = re.sub(r"\s+", " ", s).strip()
            if not re.search(r"[A-Za-z]", s):
                continue
            out.extend(_split_long(s))
    return out
