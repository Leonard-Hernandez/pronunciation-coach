import pytest

import io

from pronunciation_coach.books import (
    MAX_WORDS, SENTENCES_PER_PAGE, Paragraph, UnsupportedFormat, extract, extract_book, extract_epub,
    extract_pdf, is_chapter_heading, layout, split_paragraphs, split_sentences, text_paragraphs,
    virtual_page_count,
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

    book = extract_epub(path.read_bytes(), "t.epub")
    assert book.title == "Test Book"
    sentences = split_sentences(book.texts)
    assert "It was a bright cold day." in sentences
    assert "The clocks were striking." in sentences
    assert "Second paragraph." in sentences


def _epub(tmp_path, chapters, toc=True):
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("id1")
    book.set_title("Test Book")
    book.set_language("en")
    items = []
    for i, (title, body) in enumerate(chapters, 1):
        ch = epub.EpubHtml(title=title, file_name=f"text/ch{i}.xhtml", lang="en")
        ch.content = f"<html><body>{body}</body></html>"
        book.add_item(ch)
        items.append(ch)
    if toc:
        book.toc = [epub.Link(f"text/ch{i}.xhtml#start", title, f"ch{i}")
                    for i, (title, _) in enumerate(chapters, 1)]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *items]
    path = tmp_path / "t.epub"
    epub.write_epub(str(path), book)
    return path.read_bytes()


def test_epub_chapters_from_toc(tmp_path):
    data = _epub(tmp_path, [("The Start", "<p>First one. Second one.</p>"),
                            ("The Middle", "<h2>Ignored heading</h2><p>Third one.</p>")])
    result = layout(extract_book("t.epub", data).paragraphs)
    titles = [t for t, _ in result.chapters]
    assert titles == ["The Start", "The Middle"]
    starts = dict(result.chapters)
    assert result.sentences[starts["The Start"]] == "First one."
    assert result.sentences[starts["The Middle"]] == "Ignored heading"
    assert result.page_starts is None


def test_epub_chapters_fall_back_to_headings(tmp_path):
    data = _epub(tmp_path, [("x", "<h1>Opening</h1><p>Some text.</p>"),
                            ("y", "<p>No heading here.</p>")], toc=False)
    titles = [t for t, _ in layout(extract_book("t.epub", data).paragraphs).chapters]
    assert titles == ["Opening", "Chapter 2"]


def _pdf(pages, outline=()):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    font_ref = writer._add_object(font)
    for text in pages:
        page = writer.add_blank_page(612, 792)
        if text:
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 72 700 Td ({text}) Tj ET".encode())
            page[NameObject("/Contents")] = writer._add_object(stream)
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): font_ref})})
    for title, page_number in outline:
        writer.add_outline_item(title, page_number)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_pdf_real_pages_and_outline():
    data = _pdf(["Intro text here.", "", "Chapter text starts. More text.", "The end."],
                outline=[("Intro", 0), ("Main", 1)])
    extracted = extract_pdf(data, "b.pdf")
    assert extracted.real_pages
    result = layout(extracted.paragraphs, extracted.real_pages)
    assert result.sentences == ["Intro text here.", "Chapter text starts.", "More text.", "The end."]
    # The blank page 2 points at the next text; page 3 starts at sentence 1.
    assert result.page_starts == [0, 1, 1, 3]
    assert result.chapters == [("Intro", 0), ("Main", 1)]


def test_pdf_without_outline_has_no_chapters():
    result = layout(extract_pdf(_pdf(["One page.", "Two page."]), "b.pdf").paragraphs, True)
    assert result.chapters == [] and result.page_starts == [0, 1]


@pytest.mark.parametrize("text", ["Chapter 1", "CHAPTER IV", "Chapter One: Title", "Part 2",
                                  "Chapter Twenty-One", "CHAPTER I. Down the Rabbit-Hole"])
def test_chapter_headings(text):
    assert is_chapter_heading(text)


@pytest.mark.parametrize("text", ["Part 2 of the plan was simple.", "Chapters are long.",
                                  "Chapter 3 was boring, he said.", "The chapter ended."])
def test_not_chapter_headings(text):
    assert not is_chapter_heading(text)


def test_txt_chapters():
    text = "Preface line.\n\nChapter 1\n\nIt began. Then more.\n\nCHAPTER II: The Road\n\nOn the road."
    result = layout(text_paragraphs(text))
    assert result.chapters == [("Chapter 1", 1), ("CHAPTER II: The Road", 4)]
    assert result.sentences[4] == "CHAPTER II: The Road"


def test_empty_chapter_collapses_into_next():
    paras = [Paragraph("Part One", chapter="Part One"), Paragraph("12", chapter="Chapter 1"),
             Paragraph("Hello there.")]
    assert layout(paras).chapters == [("Part One", 0), ("Chapter 1", 1)]
    paras = [Paragraph("***", chapter="Part One"), Paragraph("Hello.", chapter="Chapter 1")]
    assert layout(paras).chapters == [("Chapter 1", 0)]


def test_virtual_page_count():
    assert virtual_page_count(0) == 1
    assert virtual_page_count(SENTENCES_PER_PAGE) == 1
    assert virtual_page_count(SENTENCES_PER_PAGE + 1) == 2
