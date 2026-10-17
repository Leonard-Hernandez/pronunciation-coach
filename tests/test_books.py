import pytest

from pronunciation_coach.books import (
    MAX_WORDS, UnsupportedFormat, extract, extract_epub, split_paragraphs, split_sentences,
)


def test_split_sentences_handles_abbreviations():
    text = "Mr. Smith went to Washington. He arrived at 3 p.m. and left. Did he stay?"
    assert split_sentences(text) == [
        "Mr. Smith went to Washington.", "He arrived at 3 p.m. and left.", "Did he stay?",
    ]


def test_split_sentences_joins_wrapped_lines_and_hyphens():
    text = "This is a sen-\ntence that wraps\nacross lines.\n\nNew paragraph here."
    assert split_sentences(text) == ["This is a sentence that wraps across lines.", "New paragraph here."]


def test_split_sentences_drops_non_text_and_normalizes_quotes():
    text = "* * *\n\n“Hello,” she said.\n\n42"
    assert split_sentences(text) == ['"Hello," she said.']


def test_long_sentences_are_split():
    long = " ".join(["word"] * (MAX_WORDS * 2 + 5)) + "."
    parts = split_sentences(long)
    assert len(parts) == 3
    assert all(len(p.split()) <= MAX_WORDS for p in parts)


def test_split_paragraphs():
    assert split_paragraphs("a\nb\n\n\nc") == ["a b", "c"]


def test_extract_txt():
    title, paras = extract("My Story.txt", "First line.\n\nSecond one.".encode())
    assert title == "My Story"
    assert paras == ["First line.", "Second one."]


def test_unsupported_format():
    with pytest.raises(UnsupportedFormat):
        extract("book.docx", b"x")


def test_extract_epub(tmp_path):
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("id1")
    book.set_title("Test Book")
    book.set_language("en")
    ch = epub.EpubHtml(title="One", file_name="ch1.xhtml", lang="en")
    ch.content = ("<html><body><h1>Chapter One</h1><p>It was a <em>bright</em> cold day.\n"
                  "The clocks were striking.</p><p>Second paragraph.</p></body></html>")
    book.add_item(ch)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", ch]
    path = tmp_path / "t.epub"
    epub.write_epub(str(path), book)

    title, paras = extract_epub(path.read_bytes(), "t.epub")
    assert title == "Test Book"
    sentences = split_sentences(paras)
    assert "It was a bright cold day." in sentences
    assert "The clocks were striking." in sentences
    assert "Second paragraph." in sentences
