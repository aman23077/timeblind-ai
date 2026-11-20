"""Author the standalone draft PDF from the report's structured Word content.

This is a ReportLab publication path, not a Word layout fidelity check.
"""
from pathlib import Path
from html import escape
from docx import Document
from docx.oxml.ns import qn
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, PageBreak, Spacer, LongTable, TableStyle
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / "output/report"
source = Document(out / "TimeBlindAI_BTP_November_Draft.docx")
styles = getSampleStyleSheet()
styles.add(ParagraphStyle("BodyAcademic", fontName="Times-Roman", fontSize=11, leading=14, alignment=TA_JUSTIFY, spaceAfter=7))
styles.add(ParagraphStyle("AcademicTitle", fontName="Times-Bold", fontSize=24, leading=29, alignment=TA_CENTER, spaceAfter=18))
styles.add(ParagraphStyle("AcademicSubtitle", fontName="Times-Roman", fontSize=15, leading=20, alignment=TA_CENTER, spaceAfter=18))
styles.add(ParagraphStyle("AcademicH1", fontName="Times-Bold", fontSize=19, leading=24, spaceAfter=18, keepWithNext=True))
styles.add(ParagraphStyle("AcademicH2", fontName="Times-Bold", fontSize=13.5, leading=17, spaceBefore=12, spaceAfter=9, keepWithNext=True))
styles.add(ParagraphStyle("AcademicCenter", parent=styles["BodyAcademic"], alignment=TA_CENTER))
styles.add(ParagraphStyle("CellAcademic", fontName="Times-Roman", fontSize=10, leading=13))
styles.add(ParagraphStyle("CellHeader", parent=styles["CellAcademic"], fontName="Times-Bold"))

class Report(BaseDocTemplate):
    def afterFlowable(self, flow):
        if isinstance(flow, Paragraph) and flow.style.name in ("AcademicH1", "AcademicH2"):
            title = flow.getPlainText()
            if title in ("Contents", "Student Declaration", "Certificate", "Abstract", "Acknowledgments", "Work Distribution"): return
            level = 0 if flow.style.name == "AcademicH1" else 1
            if level: return
            key = f"section-{self.seq.nextf('heading')}"
            self.canv.bookmarkPage(key)
            self.notify("TOCEntry", (level, title, self.page, key))

def page_art(canvas, document):
    if document.page == 1: return
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#333333"))
    canvas.setFont("Times-Roman", 9)
    canvas.drawString(64, A4[1]-40, "TimeBlindAI   |   November 2026 BTP draft   |   Participant results pending")
    canvas.drawCentredString(A4[0]/2, 36, str(document.page))
    canvas.restoreState()

pdf = Report(str(out / "TimeBlindAI_BTP_November_Draft.pdf"), pagesize=A4, leftMargin=64, rightMargin=64, topMargin=70, bottomMargin=60,
             title="TimeBlindAI Implementation and Pilot Evaluation Draft", author="Aarush Gaur and Aman Sachdeva")
pdf.addPageTemplates(PageTemplate(id="academic", frames=[Frame(64,60,A4[0]-128,A4[1]-130, leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)], onPage=page_art))
story=[]
def flow_diagram(labels, caption):
    drawing=Drawing(460,100)
    for i,(a,b) in enumerate(labels):
        x=i*117
        drawing.add(Rect(x,35,106,58,strokeColor=colors.HexColor('#64748b'),fillColor=colors.HexColor('#f1f5f9'),strokeWidth=.7))
        drawing.add(String(x+53,72,a,fontName='Times-Bold',fontSize=10,textAnchor='middle'))
        drawing.add(String(x+53,55,b,fontName='Times-Roman',fontSize=9,textAnchor='middle'))
        if i<3:
            drawing.add(Line(x+106,64,x+115,64,strokeColor=colors.black))
            drawing.add(Polygon([x+115,64,x+111,67,x+111,61],fillColor=colors.black))
    story.extend([drawing,Paragraph(escape(caption),styles['CellAcademic']),Spacer(1,14)])
paragraphs={p._p:p for p in source.paragraphs}
tables={t._tbl:t for t in source.tables}
text_parts=[]
for element in source.element.body:
    if element.tag == qn("w:p"):
        para = paragraphs[element]
        if element.xpath('.//w:br[@w:type="page"]'):
            story.append(PageBreak())
        text = para.text.strip()
        if not text: continue
        text_parts.append(text)
        name=para.style.name
        style = styles["AcademicTitle"] if name=="Title" else styles["AcademicSubtitle"] if name=="Subtitle" else styles["AcademicH1"] if name=="Heading 1" else styles["AcademicH2"] if name=="Heading 2" else styles["AcademicCenter"] if para.alignment==TA_CENTER else styles["BodyAcademic"]
        if text.startswith("Update this contents field"): continue
        text=text.replace("–", "-").replace("—", "-").replace("’", "'")
        story.append(Paragraph(escape(text), style))
        if text=='4 Architecture and Ontology Mapping':
            flow_diagram([('Browser','Next.js interface'),('API','FastAPI validation'),('Reasoning','Rules and optional AI'),('Persistence','SQLAlchemy database')], 'Figure 1  Implemented software layers. API ownership checks scope access to persistent user records.')
        if text=='6 Evaluation Methodology':
            flow_diagram([('Consent','Join the pilot'),('Predict','Save both estimates'),('Work','Time and report breaks'),('Review','Outcomes and feedback')], 'Figure 2  Prospective pilot sequence. The personal guess is saved before the app prediction is revealed.')
        if text=="Contents":
            toc=TableOfContents()
            toc.levelStyles=[ParagraphStyle("toc0",fontName="Times-Roman",fontSize=11,leading=14,spaceBefore=5)]
            story.append(toc)
    elif element.tag == qn("w:tbl"):
        t=tables[element]
        rows=[[Paragraph(escape(c.text), styles["CellHeader" if i==0 else "CellAcademic"]) for c in row.cells] for i,row in enumerate(t.rows)]
        original=[c.width for c in t.rows[0].cells]
        widths=[float(w)/sum(original)*(A4[0]-128) for w in original]
        table=LongTable(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#E8ECF0")),("GRID",(0,0),(-1,-1),.4,colors.HexColor("#D9D9D9")),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
        story.extend([table,Spacer(1,12)])
pdf.multiBuild(story)
(out/"TimeBlindAI_BTP_November_Draft.txt").write_text("\n\n".join(text_parts),encoding="utf-8")
print(out / "TimeBlindAI_BTP_November_Draft.pdf")
