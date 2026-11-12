"""Build the professor report locally using the bundled document runtime."""
import collections
import csv
import json
import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from docx.opc.constants import RELATIONSHIP_TYPE as RT

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/TimeBlindAI_Project_Explanation.md"
OUT = ROOT / "docs/TimeBlindAI_Project_Explanation.docx"

FIELDS = [
    ("task_id", "Identifier", "Links a task to sessions and steps; omitted from LLM estimation input."),
    ("user_id", "Identifier", "Scopes personal history; caller ownership still needs authentication."),
    ("title", "Input", "Task wording; sent to the model and used in conservative duplicate grouping."),
    ("task_type", "Input", "Category such as reading or assignment; supports rules and history selection."),
    ("difficulty", "Input", "User-selected easy, medium or hard; affects rules and protective buffers."),
    ("priority", "Input", "Task urgency preference; supplied to ordering, not the exported duration evaluator."),
    ("quantity_value", "Input", "Numeric scope; units are not separately exported, which creates ambiguity."),
    ("status", "Outcome or state", "Completed status is required by the strict duration audit."),
    ("deadline_at", "Input", "Optional deadline; scheduler treats it as a hard finish constraint."),
    ("created_at", "Timestamp", "Creation time used for audit ordering; not a task completion timestamp."),
    ("estimated_minutes", "Prediction", "Saved starting estimate or prior prediction; method provenance is not recorded here."),
    ("actual_minutes", "Target", "Recorded task elapsed minutes; audit requires positive values and completed status."),
    ("estimate_error_minutes", "Derived outcome", "Actual minus estimate; positive means an underestimate. Never a prospective input."),
    ("actual_to_estimate_ratio", "Derived outcome", "Actual divided by estimate; an outcome-based evaluation value."),
    ("completed_session_count", "Outcome", "Count for the target task is unknown at creation and leaks future information."),
    ("total_elapsed_minutes", "Outcome", "Sum of recorded completed session elapsed minutes; requires careful time semantics."),
    ("avg_delay_minutes", "Outcome", "Average delay for completed sessions; prior tasks can inform protective buffers."),
    ("avg_overrun_minutes", "Outcome", "Average overrun; valid historical context only if known before prediction."),
    ("latest_difficulty_feedback", "Feedback", "Last completed-session assessment; collected after work, not before it."),
    ("latest_feedback_reasons", "Feedback", "Comma-separated reasons such as interruption; omitted from LLM history."),
    ("latest_feedback_notes", "Free text", "Potentially identifying notes; excluded from LLM requests and this row appendix."),
]


def prepare_appendices():
    path = ROOT / "data/training/timeblind_training_data.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig", newline="")))
    outcomes = {}
    seen = set()
    for index, row in sorted(enumerate(rows), key=lambda pair: pair[1]["created_at"]):
        try:
            actual, estimate = int(row["actual_minutes"]), int(row["estimated_minutes"])
        except (ValueError, TypeError):
            outcomes[index] = "Missing"
            continue
        if row["status"] != "completed":
            outcomes[index] = "Pending"
            continue
        if not 1 <= actual <= 1440 or not 5 <= estimate <= 1440:
            outcomes[index] = "Bounds"
            continue
        key = (row["user_id"], row["title"].strip().lower(), row["created_at"][:10])
        if key in seen:
            outcomes[index] = "Repeat"
            continue
        seen.add(key)
        outcomes[index] = "Use"
    users = {uid: f"U{i + 1}" for i, uid in enumerate(dict.fromkeys(row["user_id"] for row in rows))}
    lines = ["Rows follow the original CSV order. R01 is the first data row after the header. User labels are pseudonyms local to this report. Times are minutes. n.a. means missing, not zero. Audit labels: Use = eligible; Missing = missing estimate or actual; Pending = not completed; Repeat = conservative same-user/title/day exclusion.",
             "", "| Row | User | Type | Estimate | Actual | Status | Audit |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for i, row in enumerate(rows):
        lines.append(f"| R{i + 1:02d} | {users[row['user_id']]} | {row['task_type']} | {row['estimated_minutes'] or 'n.a.'} | {row['actual_minutes'] or 'n.a.'} | {row['status']} | {outcomes[i]} |")
    counts = collections.Counter(outcomes.values())
    assert len(rows) == 47 and counts["Use"] == 28 and len(users) == 7
    eligible = sorted([i for i in outcomes if outcomes[i] == "Use"], key=lambda i: rows[i]["created_at"])
    holdout = eligible[int(len(eligible) * .8):]
    lines += ["", "The chronological holdout maps to the appendix as " + ", ".join(f"H{j + 1} = R{i + 1:02d}" for j, i in enumerate(holdout)) + "."]
    dictionary = ["The role describes whether a value is available before a new task starts. Historical outcomes may be useful only when they belong to earlier tasks and precede the prediction.",
                  "", "| Field | Role | Meaning and use |", "| --- | --- | --- |"]
    dictionary += [f"| `{field}` | {role} | {meaning} |" for field, role, meaning in FIELDS]
    return "\n".join(lines), "\n".join(dictionary)


def inline(paragraph, text):
    pattern = r"(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?://[^)]+\))"
    for part in re.split(pattern, text):
        if not part:
            continue
        link = re.fullmatch(r"\[([^\]]+)\]\((https?://[^)]+)\)", part)
        if link:
            element = OxmlElement("w:hyperlink")
            element.set(qn("r:id"), paragraph.part.relate_to(link[2], RT.HYPERLINK, is_external=True))
            run = OxmlElement("w:r")
            props = OxmlElement("w:rPr")
            color = OxmlElement("w:color"); color.set(qn("w:val"), "24466B"); props.append(color)
            run.append(props)
            value = OxmlElement("w:t"); value.text = link[1]; run.append(value)
            element.append(run); paragraph._p.append(element)
        else:
            run = paragraph.add_run(part[2:-2] if part.startswith("**") else part[1:-1] if part.startswith("`") else part)
            if part.startswith("**"):
                run.bold = True
            elif part.startswith("`"):
                run.font.name = "Consolas"
                run.font.size = Pt(9.5)


def add_table(doc, data):
    columns = len(data[0])
    if columns == 7:
        widths = [.40, .43, 1.18, .62, .62, .91, .66]
    elif columns == 3:
        widths = ([1.25, 2.20, 3.00] if data[0][0] == "Area" else [2.30, .95, 3.20])
    elif columns == 6:
        widths = [6.45 / columns] * columns
    elif columns == 5:
        widths = ([.75, .68, 1.15, 1.98, 1.89] if data[0][0] == "Holdout row"
                  else [2.35, 1.0, 1.0, 1.0, 1.1])
    elif columns == 2:
        widths = [3.15, 3.30]
    else:
        widths = [.86] + [(6.45 - .86) / (columns - 1)] * (columns - 1)
    table = doc.add_table(rows=1, cols=columns)
    table.autofit = False
    for col, width in zip(table.columns, widths):
        col.width = Inches(width)
    properties = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = OxmlElement(f"w:{side}"); border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), "4"); border.set(qn("w:color"), "D9D9D9"); borders.append(border)
    properties.append(borders)
    for i, values in enumerate(data):
        cells = table.rows[0].cells if i == 0 else table.add_row().cells
        row_props = table.rows[i]._tr.get_or_add_trPr()
        no_split = OxmlElement("w:cantSplit"); row_props.append(no_split)
        if i == 0:
            repeat = OxmlElement("w:tblHeader"); row_props.append(repeat)
        for j, (cell, value, width) in enumerate(zip(cells, values, widths)):
            cell.width = Inches(width)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            margin = OxmlElement("w:tcMar")
            for side, size in (("top", "85"), ("bottom", "85"), ("left", "90"), ("right", "90")):
                node = OxmlElement(f"w:{side}"); node.set(qn("w:w"), size); node.set(qn("w:type"), "dxa"); margin.append(node)
            cell._tc.get_or_add_tcPr().append(margin)
            if i == 0:
                fill = OxmlElement("w:shd"); fill.set(qn("w:fill"), "E9EEF4"); cell._tc.get_or_add_tcPr().append(fill)
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = 1.08
            if columns in (5, 7) and j > 0 and j != (2 if columns == 7 else -1):
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            inline(paragraph, value)
            for run in paragraph.runs:
                run.font.size = Pt(9.6 if columns >= 5 else 10)
                run.bold = i == 0 or run.bold
    doc.add_paragraph().paragraph_format.space_after = Pt(3)


def main():
    rows, dictionary = prepare_appendices()
    markdown = SOURCE.read_text(encoding="utf-8").replace("{{DATA_ROWS}}", rows).replace("{{DATA_DICTIONARY}}", dictionary)
    SOURCE.write_text(markdown, encoding="utf-8")
    doc = Document()
    # Bundled templates can carry a decorative title border. Remove that residue.
    for node in list(doc.styles.element.iter(qn("w:pBdr"))):
        node.getparent().remove(node)
    section = doc.sections[0]
    section.page_width, section.page_height = Inches(8.27), Inches(11.69)
    section.top_margin = section.bottom_margin = Inches(.72)
    section.left_margin = section.right_margin = Inches(.86)
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"; normal.font.size = Pt(11)
    normal.font.color.rgb = RGBColor(0, 0, 0)
    normal.paragraph_format.space_after = Pt(7)
    normal.paragraph_format.line_spacing = 1.12
    for name, size in (("Title", 27), ("Subtitle", 12), ("Heading 1", 16), ("Heading 2", 13)):
        style = doc.styles[name]
        style.font.name = "Calibri"; style.font.size = Pt(size)
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.font.underline = False
        style.paragraph_format.space_before = Pt(15 if name.startswith("Heading") else 0)
        style.paragraph_format.space_after = Pt(7)
        if name.startswith("Heading"):
            style.paragraph_format.keep_with_next = True
    doc.core_properties.title = "TimeBlindAI project explanation"
    doc.core_properties.subject = "AI integration datasets scheduling evaluation and next steps"
    doc.core_properties.author = "TimeBlindAI"
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("TimeBlindAI  |  ").font.size = Pt(9)
    field = OxmlElement("w:fldSimple"); field.set(qn("w:instr"), "PAGE"); footer._p.append(field)
    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1; continue
        if line.startswith("# "):
            doc.add_paragraph(line[2:], "Title")
        elif line.startswith("## "):
            doc.add_heading(line[3:], level=1)
        elif line.startswith("| "):
            data = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [cell.strip() for cell in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", cell) for cell in cells):
                    data.append(cells)
                i += 1
            add_table(doc, data)
            continue
        else:
            paragraph = doc.add_paragraph()
            inline(paragraph, line)
        i += 1
    doc.save(OUT)
    print(json.dumps({"document": str(OUT), "words": len(markdown.split()), "dataset_rows": 47,
                      "field_definitions": len(FIELDS), "tables": len(doc.tables)}))


if __name__ == "__main__":
    main()
