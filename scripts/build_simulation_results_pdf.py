"""Render the actual saved simulation and live-check artifacts as a results brief."""
import json
from pathlib import Path
from html import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.table import Table as WordTable
from docx.text.paragraph import Paragraph as WordParagraph

ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/"output/simulation"
data=json.loads((folder/"simulation-results.json").read_text(encoding="utf-8"))
live=json.loads((folder/"live-ai-check.json").read_text(encoding="utf-8"))
benchmark=json.loads((folder/"benchmark/report.json").read_text(encoding="utf-8"))
styles=getSampleStyleSheet()
styles.add(ParagraphStyle("BodyReport",fontName="Helvetica",fontSize=10.5,leading=15,spaceAfter=9))
styles.add(ParagraphStyle("CellReport",fontName="Helvetica",fontSize=9,leading=12))
for name in ["Title","Heading1","Heading2"]:
    styles[name].textColor=colors.black
story=[]
editable=Document()
section=editable.sections[0]
section.page_width,section.page_height=Inches(8.2677), Inches(11.6929)
section.left_margin=section.right_margin=Inches(.75)
section.top_margin=section.bottom_margin=Inches(.65)
for name in ("Normal","Title","Heading 1"):
    style=editable.styles[name]
    style.font.name="Arial";style.font.color.rgb=RGBColor(0,0,0)
editable.styles["Normal"].font.size=Pt(11)
editable.styles["Normal"].paragraph_format.space_after=Pt(8)
editable.styles["Normal"].paragraph_format.line_spacing=1.12
footer=section.footer.paragraphs[0]
footer.text="SYNTHETIC COHORT | NOT HUMAN PILOT RESULTS    "
footer.runs[0].font.size=Pt(8)
page_field=OxmlElement("w:fldSimple");page_field.set(qn("w:instr"),"PAGE");footer._p.append(page_field)
def new_page():
    story.append(PageBreak());editable.add_page_break()
def p(text):
    story.append(Paragraph(escape(text),styles["BodyReport"]))
    editable.add_paragraph(text)
def heading(text):
    story.append(Paragraph(text,styles["Heading1"]));story.append(Spacer(1,9))
    editable.add_heading(text,1)
def table(headers,rows,widths):
    native=editable.add_table(rows=1, cols=len(headers))
    native.autofit=False
    for cell,label in zip(native.rows[0].cells,headers):cell.text=str(label)
    repeat=OxmlElement("w:tblHeader");native.rows[0]._tr.get_or_add_trPr().append(repeat)
    for row in rows:
        for cell,value in zip(native.add_row().cells,row):cell.text=str(value)
    for i,row in enumerate(native.rows):
        for j,cell in enumerate(row.cells):
            cell.width=Inches(widths[j]/72)
            cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            pr=cell._tc.get_or_add_tcPr()
            borders=OxmlElement("w:tcBorders")
            for side in ("top","left","bottom","right"):
                b=OxmlElement("w:"+side)
                for k,v in (("val","single"),("sz","4"),("color","CBD5E1")):b.set(qn("w:"+k),v)
                borders.append(b)
            pr.append(borders)
            margins=OxmlElement("w:tcMar")
            for side in ("top","left","bottom","right"):
                m=OxmlElement("w:"+side);m.set(qn("w:w"),"80");m.set(qn("w:type"),"dxa");margins.append(m)
            pr.append(margins)
            if i==0:
                shade=OxmlElement("w:shd");shade.set(qn("w:fill"),"E2E8F0");pr.append(shade)
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after=Pt(1)
                paragraph.paragraph_format.line_spacing=1.05
                for run in paragraph.runs:run.font.size=Pt(9.5);run.bold=i==0
    values=[[Paragraph(escape(str(v)),styles["CellReport"]) for v in row] for row in [headers]+rows]
    t=Table(values,colWidths=widths,repeatRows=1,hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#E2E8F0")),("GRID",(0,0),(-1,-1),.4,colors.HexColor("#CBD5E1")),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6)]))
    story.extend([t,Spacer(1,14)])
story.append(Paragraph("TimeBlindAI Simulation Results",styles["Title"]))
editable.add_paragraph("TimeBlindAI Simulation Results","Title")
p("November 23, 2026 | Generated demonstration cohort and measured software checks")
p("This is not a human participant study. Profiles, tasks, elapsed durations and desktop intervals were generated and labelled synthetic. No provided recruitment email addresses, invented consent, subjective ratings or real-person identities were used.")
table(["Database records","Count"],[("Simulation profiles",data["simulation_profiles"]),("Generated tasks",data["tasks"]),("Completed synthetic tasks",data["statuses"]["completed"]),("Unfinished / missed / pending","19 / 19 / 19"),("Simulated sessions",data["sessions"]),("Generated schedules",data["schedules"]),("Synthetic desktop intervals",data["simulated_activity_intervals"]),("Computed profile summaries",data["computed_reviews"]),("Observed human participants / reviews","0 / 0")],[330,155])
heading("Duration results under the generator")
m=data["estimation"]
p(f"On {m['n']} completed synthetic tasks, the production rules baseline had mean absolute error {m['mae_minutes']} minutes, bias {m['bias_actual_minus_estimate_minutes']} minutes (simulated actual minus estimate), and {m['within_15_minutes_percent']}% of estimates within 15 minutes. Actual-denominator MAPE was {m['mape_actual_denominator_percent']}%.")
p("These values characterize the generator and rules baseline, not student performance, LLM prediction quality, participant satisfaction or an observed productivity benefit.")
new_page();heading("Generated profile results")
p("Each label represents a generated profile, not an enrolled person. Five completed synthetic tasks per profile contribute to duration error. No login credentials were created for these profiles.")
table(["Synthetic profile","Tasks","Completed N","Rules MAE min","Within 15 min %"],[(r["label"].replace("SYNTHETIC ",""),r["tasks"],r["estimation"]["n"],r["estimation"]["mae_minutes"],r["estimation"]["within_15_minutes_percent"]) for r in data["people"]],[125,65,85,100,110])
p("The generator uses category workload assumptions, difficulty, profile speed, lognormal variation and interruptions. This is an illustrative sensitivity dataset, not a calibrated model of a student population.")
new_page();heading("Category and activity summaries")
table(["Category","Completed N","Rules MAE min","Within 15 min %"],[(k,v["n"],v["mae_minutes"],v["within_15_minutes_percent"]) for k,v in data["categories"].items()],[155,100,115,115])
p(f"The stored desktop fixtures contain {data['simulated_app_switches']} simulated app transitions, {data['simulated_active_seconds']/60:.2f} simulated active minutes and {data['simulated_idle_seconds']/60:.2f} simulated idle minutes. Each session has only a short generated excerpt; these are not complete desktop observations or verified distractions.")
p("Activity totals are computed by the application's existing activity-summary implementation. Generated executable names do not establish context-switching cost, attention, cognitive load or wasted time. No screen recording or real desktop collection was performed for this dataset.")
heading("Computed summaries rather than invented reviews")
p("Nineteen per-profile summaries describe computed error on synthetic records. They are deterministic summaries, not LLM-generated reviews and not participant ratings. No recommendation acceptance rate, usefulness score, TDI diagnosis or energy-effect finding is claimed.")
new_page();heading("Measured software and provider checks")
table(["Check","Observed result","Evidence limit"],[("Demo schedule checks",f"{data['nonoverlap_positive_duration_passes']}/{data['schedules']} pass non-overlap and positive duration","Production rules planner, synthetic inputs"),("Separate policy and scheduler benchmark",f"{benchmark['checks_passed']}/{benchmark['checks_total']} specified checks passed","23 policy scenarios and 12 scheduler scenarios; not a human experiment"),("Live Groq requests",f"{live['successes']}/{live['attempts']} successful","Two synthetic task inputs; tiny integration sample"),("Live model",live["model"],"No real participant task history supplied")],[155,145,185])
for i,r in enumerate(live["results"],1):
    p(f"Live request {i}: status {r['status']}; latency {r['latency_seconds']} seconds; AI estimate {r.get('ai_minutes','not returned')} minutes. The comparison outcome is generated, not human work time.")
heading("How to use these results")
p("Use this brief for an engineering demonstration: persistence, linked records, dynamic analytics, scheduler conformance and live integration. Report the real participant pilot separately, including observed participation, honest timing provenance, matching prediction cohorts and actual reviews.")
p("Local dashboard: /admin/simulation, using an existing administrator login. The same route on Render requires deployment of the code and explicit seeding of the hosted database. Local seeding does not update Render. Real pilot analytics exclude synthetic-provenance accounts.")
p("Source artifacts: simulation-results.json; live-ai-check.json; benchmark/report.json. Seed: 23077. Dataset: btp-demo-2026-11-v1. Original database records were checked against the pre-seed backup and remained unchanged.")
def footer(canvas,doc):
    canvas.setFont("Helvetica",8)
    canvas.drawString(54,27,"SYNTHETIC COHORT | NOT HUMAN PILOT RESULTS")
    canvas.drawRightString(A4[0]-54,27,str(doc.page))
pdf=folder/"Simulation_Results.pdf"
SimpleDocTemplate(str(pdf),pagesize=A4,leftMargin=54,rightMargin=54,topMargin=48,bottomMargin=48,title="TimeBlindAI Synthetic Demonstration Results").build(story,onFirstPage=footer,onLaterPages=footer)
print(pdf)
try:
    editable.save(folder/"Simulation_Results.docx")
    print(folder/"Simulation_Results.docx")
except PermissionError:
    print("Word has the DOCX open; preserving that copy and writing the editable RTF below.")

# Native text and table cells remain editable in Word without a DOCX import.
def rtf_text(value):
    result=[]
    for char in value:
        if char in "\\{}":
            result.append("\\"+char)
        elif char == "\n":
            result.append(r"\line ")
        elif ord(char) < 128:
            result.append(char)
        else:
            encoded=char.encode("utf-16-le")
            for offset in range(0,len(encoded),2):
                code=int.from_bytes(encoded[offset:offset+2],"little",signed=True)
                result.append("\\u"+str(code)+"?")
    return "".join(result)

rtf=[r"{\rtf1\ansi\deff0{\fonttbl{\f0 Arial;}}\paperw11906\paperh16838\margl1080\margr1080\margt936\margb936",
     r"{\footer\pard\fs16 SYNTHETIC COHORT | NOT HUMAN PILOT RESULTS\tab {\field{\*\fldinst PAGE}}\par}"]
for element in editable.element.body:
    if element.tag == qn("w:p"):
        paragraph=WordParagraph(element,editable)
        if any(b.get(qn("w:type")) == "page" for b in element.iter(qn("w:br"))):
            rtf.append(r"\page")
        if not paragraph.text:
            continue
        style=paragraph.style.name
        size=40 if style == "Title" else 28 if style.startswith("Heading") else 22
        bold=style == "Title" or style.startswith("Heading")
        rtf.append(r"\pard\sb0\sa160\fs"+str(size)+(r"\b " if bold else " ")+rtf_text(paragraph.text)+r"\b0\par")
    elif element.tag == qn("w:tbl"):
        native=WordTable(element,editable)
        widths=[cell.width or Inches(1) for cell in native.rows[0].cells]
        edges=[];edge=0
        for width in widths:
            edge+=round(int(width)/sum(int(w) for w in widths)*9700)
            edges.append(edge)
        for index,row in enumerate(native.rows):
            rtf.append(r"\trowd\trgaph80")
            for edge in edges:
                rtf.append(r"\clvertalc\clbrdrt\brdrs\brdrw4\clbrdrl\brdrs\brdrw4\clbrdrb\brdrs\brdrw4\clbrdrr\brdrs\brdrw4\cellx"+str(edge))
            for cell in row.cells:
                rtf.append(r"\pard\intbl\fs19 "+(r"\b " if index == 0 else "")+rtf_text(cell.text)+r"\b0\cell")
            rtf.append(r"\row")
        rtf.append(r"\pard\sa120\par")
rtf.append("}")
rtf_path=folder/"Simulation_Results_Editable.rtf"
rtf_path.write_text("\n".join(rtf),encoding="ascii")
print(rtf_path)
