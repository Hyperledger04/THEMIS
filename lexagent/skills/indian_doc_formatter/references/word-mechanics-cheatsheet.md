# python-docx Mechanics Cheatsheet

Key patterns for Word-native features. Use these exact patterns in write_docx
to produce documents that behave correctly in Word (not just look correct as
static PDFs).

## Multi-Level List (Clause Numbering)

```python
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

# Define numbering in document's numbering part — call once per document
def add_multilevel_numbering(doc):
    numbering = doc.part.numbering_part.numbering_definitions._element
    abstractNum = OxmlElement("w:abstractNum")
    abstractNum.set(qn("w:abstractNumId"), "1")
    # Level 0: 1. 2. 3.
    lvl0 = _make_level(0, "decimal", "%1.", "left", 360)
    # Level 1: 1.1 1.2
    lvl1 = _make_level(1, "decimal", "%1.%2.", "left", 720)
    # Level 2: 1.1.1
    lvl2 = _make_level(2, "decimal", "%1.%2.%3.", "left", 1080)
    # Level 3: (a) (b)
    lvl3 = _make_level(3, "lowerLetter", "(%4)", "left", 1440)
    for lvl in [lvl0, lvl1, lvl2, lvl3]:
        abstractNum.append(lvl)
    numbering.append(abstractNum)
```

## Bookmarks (for Cross-Reference Targets)

```python
def add_bookmark(paragraph, bookmark_id: int, name: str):
    """Add a Word bookmark at the start of a paragraph."""
    run = paragraph.runs[0] if paragraph.runs else paragraph.add_run()
    tag = run._r
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(bookmark_id))
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(bookmark_id))
    tag.insert(0, start)
    tag.addnext(end)
```

## REF Fields (Cross-Reference Insertion)

```python
def add_ref_field(paragraph, bookmark_name: str, display_text: str):
    """Insert a Word REF field — updates automatically when numbering changes."""
    run = paragraph.add_run()
    fldChar_begin = OxmlElement("w:fldChar")
    fldChar_begin.set(qn("w:fldCharType"), "begin")
    instrText = OxmlElement("w:instrText")
    instrText.text = f' REF {bookmark_name} \\n \\h '
    fldChar_end = OxmlElement("w:fldChar")
    fldChar_end.set(qn("w:fldCharType"), "end")
    run._r.append(fldChar_begin)
    run._r.append(instrText)
    run._r.append(fldChar_end)
```

## Auto-TOC Field

```python
def insert_toc(doc):
    """Insert a TOC field — Word populates/updates it on open."""
    para = doc.add_paragraph()
    run = para.add_run()
    fldChar = OxmlElement("w:fldChar")
    fldChar.set(qn("w:fldCharType"), "begin")
    instrText = OxmlElement("w:instrText")
    instrText.set(qn("xml:space"), "preserve")
    instrText.text = 'TOC \\o "1-3" \\h \\z \\u'
    fldChar_end = OxmlElement("w:fldChar")
    fldChar_end.set(qn("w:fldCharType"), "end")
    run._r.append(fldChar)
    run._r.append(instrText)
    run._r.append(fldChar_end)
```

## Page Numbers in Footer (Page X of Y)

```python
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

def add_page_number_footer(doc):
    section = doc.sections[0]
    footer = section.footer
    para = footer.paragraphs[0]
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    # "Page "
    para.add_run("Page ")
    # PAGE field
    _add_field(para, "PAGE")
    para.add_run(" of ")
    # NUMPAGES field
    _add_field(para, "NUMPAGES")

def _add_field(para, field_name: str):
    run = para.add_run()
    fldChar = OxmlElement("w:fldChar")
    fldChar.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" {field_name} "
    fldChar_end = OxmlElement("w:fldChar")
    fldChar_end.set(qn("w:fldCharType"), "end")
    run._r.append(fldChar)
    run._r.append(instr)
    run._r.append(fldChar_end)
```

## Two-Column Signature Block Table

```python
def add_signature_block(doc, parties: list[str]):
    """parties: list of party names, one column per party."""
    table = doc.add_table(rows=6, cols=len(parties))
    table.style = "Table Grid"
    # Remove borders
    for row in table.rows:
        for cell in row.cells:
            tc = cell._tc
            tcPr = tc.get_or_add_tcPr()
            tcBorders = OxmlElement("w:tcBorders")
            for border in ["top","left","bottom","right","insideH","insideV"]:
                b = OxmlElement(f"w:{border}")
                b.set(qn("w:val"), "none")
                tcBorders.append(b)
            tcPr.append(tcBorders)
    # Row 0: "For and on behalf of [PARTY]"
    for i, party in enumerate(parties):
        table.rows[0].cells[i].text = f"For and on behalf of\n{party}"
    # Row 1: blank (signature line space)
    # Row 2: signature line
    for i in range(len(parties)):
        table.rows[2].cells[i].text = "________________________"
    # Rows 3-5: Name / Designation / Date / Place
    for i in range(len(parties)):
        table.rows[3].cells[i].text = "Name:"
        table.rows[4].cells[i].text = "Designation:\nDate:\nPlace:"
```
