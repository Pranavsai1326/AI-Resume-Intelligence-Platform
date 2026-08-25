"""DOCX extraction via python-docx (ADR structure: SECURITY.md section 2).

The zip container is bounds-checked by :func:`app.documents.upload.validate_docx_structure`
before this module ever opens it. Header/footer detection, column count and text-box markers are
read from the raw ``word/document.xml`` part with ``defusedxml`` (external entities and DTDs
disabled) rather than trusted to any single library's parser for this security-sensitive pass;
python-docx itself is used only for the structural text extraction it is designed for.
"""

from __future__ import annotations

import zipfile
from collections.abc import Iterator, Sequence
from io import BytesIO

from defusedxml.ElementTree import fromstring as safe_fromstring
from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.core.errors import CorruptDocumentError
from app.documents.extract.base import ExtractionResult, LayoutSignals
from app.documents.upload import DocumentKind, validate_docx_structure

_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
#: Local (namespace-stripped) tag names that indicate a floating text box in either the legacy
#: VML drawing format or modern DrawingML.
_TEXT_BOX_LOCAL_NAMES = frozenset({"txbxContent", "pict"})


def _iter_block_items(document: DocxDocument) -> Iterator[Paragraph | Table]:
    """Paragraphs and tables in document order - python-docx does not expose this directly."""
    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


#: A genuine small reference table ("Skill | Level") rarely runs this many rows; a table used as
#: a page-layout device (a very common way to build a sidebar-plus-main-column resume in Word,
#: since DOCX has no native CSS-style column layout most templates would actually want) typically
#: spans most of the page. This distinguishes the two rather than guessing from formatting alone.
_LAYOUT_TABLE_MIN_ROWS = 4


def _table_text(table: Table) -> str:
    """Row-major for an ordinary small data table; column-major for a likely layout table.

    Joining every row's cells with " | " is correct for a real data table, but wrong for a table
    used to lay out a sidebar next to a main column: "Jordan Vance | EXPERIENCE" from a name in
    the left cell and a section header in the right cell of the same row, interleaving two
    logically separate columns onto one line - the DOCX equivalent of the reading-order bug
    Phase 9C found and fixed for multi-column PDFs. Reading one full column before the next
    avoids it.
    """
    if len(table.rows) >= _LAYOUT_TABLE_MIN_ROWS and len(table.columns) >= 2:
        try:
            column_count = len(table.columns)
            columns_text = []
            for col_index in range(column_count):
                column_lines = [row.cells[col_index].text.strip() for row in table.rows]
                column_text = "\n".join(line for line in column_lines if line)
                if column_text:
                    columns_text.append(column_text)
            return "\n\n".join(columns_text)
        except IndexError:
            pass  # A ragged/merged-cell table doesn't fit this shape - fall back below.

    rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows]
    return "\n".join(row for row in rows if row.strip())


def _has_text(paragraphs: Sequence[Paragraph]) -> bool:
    return any(p.text.strip() for p in paragraphs)


def _detect_columns_and_textboxes(data: bytes) -> tuple[bool, bool]:
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            xml_bytes = archive.read("word/document.xml")
    except KeyError:
        return False, False

    root = safe_fromstring(xml_bytes)

    multi_column = False
    for cols in root.iter(f"{_WORD_NS}cols"):
        num = cols.get(f"{_WORD_NS}num")
        if num and num.isdigit() and int(num) > 1:
            multi_column = True
            break

    has_text_box = any(
        element.tag.split("}")[-1] in _TEXT_BOX_LOCAL_NAMES for element in root.iter()
    )
    return multi_column, has_text_box


def extract_docx(data: bytes) -> ExtractionResult:
    validate_docx_structure(data)

    try:
        document = Document(BytesIO(data))
    except Exception as exc:
        raise CorruptDocumentError from exc

    parts: list[str] = []
    for block in _iter_block_items(document):
        if isinstance(block, Paragraph):
            if block.text.strip():
                parts.append(block.text)
        else:
            table_text = _table_text(block)
            if table_text:
                parts.append(table_text)

    has_header_footer_text = any(
        _has_text(section.header.paragraphs) or _has_text(section.footer.paragraphs)
        for section in document.sections
    )
    multi_column, has_text_box = _detect_columns_and_textboxes(data)
    # A layout table (see _table_text) is multi-column just as much as a native Word "Format ->
    # Columns" section is - both put visually separate content side by side, which is exactly
    # the formatting-risk signal `multi_column` exists to report (ATS parsing simulation).
    multi_column = multi_column or any(
        len(table.rows) >= _LAYOUT_TABLE_MIN_ROWS and len(table.columns) >= 2
        for table in document.tables
    )

    return ExtractionResult(
        kind=DocumentKind.DOCX,
        text="\n\n".join(parts).strip(),
        pages=None,
        layout=LayoutSignals(
            multi_column=multi_column,
            has_tables=len(document.tables) > 0,
            has_images=len(document.inline_shapes) > 0,
            has_text_boxes=has_text_box,
            has_repeating_header_footer=has_header_footer_text,
        ),
    )
