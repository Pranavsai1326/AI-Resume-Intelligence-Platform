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


def _table_text(table: Table) -> str:
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
