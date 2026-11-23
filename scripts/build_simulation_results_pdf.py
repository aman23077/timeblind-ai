"""Render the actual saved simulation and live-check artifacts as a results brief."""
import json
from pathlib import Path
from html import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle

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
def p(text):story.append(Paragraph(escape(text),styles["BodyReport"]))
def heading(text):story.append(Paragraph(text,styles["Heading1"]));story.append(Spacer(1,9))
def table(headers,rows,widths):
    values=[[Paragraph(escape(str(v)),styles["CellReport"]) for v in row] for row in [headers]+rows]
    t=Table(values,colWidths=widths,repeatRows=1,hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#E2E8F0")),("GRID",(0,0),(-1,-1),.4,colors.HexColor("#CBD5E1")),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6)]))
    story.extend([t,Spacer(1,14)])
story.append(Paragraph("TimeBlindAI Simulation Results",styles["Title"]))
p("November 23, 2026 | Generated demonstration cohort and measured software checks")
p("This is not a human participant study. Profiles, tasks, elapsed durations and desktop intervals were generated and labelled synthetic. No provided recruitment email addresses, invented consent, subjective ratings or real-person identities were used.")
table(["Database records","Count"],[("Simulation profiles",data["simulation_profiles"]),("Generated tasks",data["tasks"]),("Completed synthetic tasks",data["statuses"]["completed"]),("Unfinished / missed / pending","19 / 19 / 19"),("Simulated sessions",data["sessions"]),("Generated schedules",data["schedules"]),("Synthetic desktop intervals",data["simulated_activity_intervals"]),("Computed profile summaries",data["computed_reviews"]),("Observed human participants / reviews","0 / 0")],[330,155])
heading("Duration results under the generator")
m=data["estimation"]
p(f"On {m['n']} completed synthetic tasks, the production rules baseline had mean absolute error {m['mae_minutes']} minutes, bias {m['bias_actual_minus_estimate_minutes']} minutes (simulated actual minus estimate), and {m['within_15_minutes_percent']}% of estimates within 15 minutes. Actual-denominator MAPE was {m['mape_actual_denominator_percent']}%.")
p("These values characterize the generator and rules baseline, not student performance, LLM prediction quality, participant satisfaction or an observed productivity benefit.")
story.append(PageBreak());heading("Generated profile results")
p("Each label represents a generated profile, not an enrolled person. Five completed synthetic tasks per profile contribute to duration error. No login credentials were created for these profiles.")
table(["Synthetic profile","Tasks","Completed N","Rules MAE min","Within 15 min %"],[(r["label"].replace("SYNTHETIC ",""),r["tasks"],r["estimation"]["n"],r["estimation"]["mae_minutes"],r["estimation"]["within_15_minutes_percent"]) for r in data["people"]],[125,65,85,100,110])
p("The generator uses category workload assumptions, difficulty, profile speed, lognormal variation and interruptions. This is an illustrative sensitivity dataset, not a calibrated model of a student population.")
story.append(PageBreak());heading("Category and activity summaries")
table(["Category","Completed N","Rules MAE min","Within 15 min %"],[(k,v["n"],v["mae_minutes"],v["within_15_minutes_percent"]) for k,v in data["categories"].items()],[155,100,115,115])
p(f"The stored desktop fixtures contain {data['simulated_app_switches']} simulated app transitions, {data['simulated_active_seconds']/60:.2f} simulated active minutes and {data['simulated_idle_seconds']/60:.2f} simulated idle minutes. Each session has only a short generated excerpt; these are not complete desktop observations or verified distractions.")
p("Activity totals are computed by the application's existing activity-summary implementation. Generated executable names do not establish context-switching cost, attention, cognitive load or wasted time. No screen recording or real desktop collection was performed for this dataset.")
heading("Computed summaries rather than invented reviews")
p("Nineteen per-profile summaries describe computed error on synthetic records. They are deterministic summaries, not LLM-generated reviews and not participant ratings. No recommendation acceptance rate, usefulness score, TDI diagnosis or energy-effect finding is claimed.")
story.append(PageBreak());heading("Measured software and provider checks")
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
