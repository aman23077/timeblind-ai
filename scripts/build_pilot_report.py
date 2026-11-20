"""Build the editable November BTP draft. Never manufactures pilot results.

Run with the bundled document Python runtime. The draft deliberately retains
pending study fields; it must be updated and signed before submission.
"""
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/report"
OUT.mkdir(parents=True, exist_ok=True)
doc = Document()
section = doc.sections[0]
# The reference uses an A4 academic thesis layout.
section.page_width, section.page_height = Inches(8.2677), Inches(11.6929)
section.top_margin = section.bottom_margin = Inches(1)
section.left_margin = section.right_margin = Inches(1)
normal = doc.styles["Normal"]
normal.font.name, normal.font.size = "Times New Roman", Pt(12)
normal.paragraph_format.line_spacing = 1.18
normal.paragraph_format.space_after = Pt(8)
for name, size in [("Title", 24), ("Subtitle", 14), ("Heading 1", 20), ("Heading 2", 14), ("Heading 3", 12)]:
    style = doc.styles[name]
    style.font.name, style.font.size, style.font.color.rgb = "Times New Roman", Pt(size), RGBColor(0, 0, 0)
    style.paragraph_format.space_before = Pt(14)
    style.paragraph_format.space_after = Pt(10)
header = section.header.paragraphs[0]
header.text = "TimeBlindAI     November 2026 BTP report draft"
header.runs[0].font.size = Pt(9)
footer = section.footer.paragraphs[0]
footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
field = OxmlElement("w:fldSimple")
field.set(qn("w:instr"), "PAGE")
footer._p.append(field)
section.different_first_page_header_footer = True


def p(text, style=None):
    paragraph = doc.add_paragraph(text, style)
    if style is None:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    return paragraph


def page(title, text=""):
    doc.add_page_break()
    doc.add_heading(title, 1)
    if text:
        for paragraph in text.strip().split("\n\n"):
            p(paragraph.strip())


def sub(title, text):
    doc.add_heading(title, 2)
    for paragraph in text.strip().split("\n\n"):
        p(paragraph.strip())


def table(headers, rows, widths):
    t = doc.add_table(rows=1, cols=len(headers))
    t.autofit = False
    for cell, name, width in zip(t.rows[0].cells, headers, widths):
        cell.text, cell.width = name, Inches(width)
    repeat = OxmlElement("w:tblHeader")
    t.rows[0]._tr.get_or_add_trPr().append(repeat)
    for row in rows:
        cells = t.add_row().cells
        for cell, value, width in zip(cells, row, widths):
            cell.text, cell.width = str(value), Inches(width)
    for i, row in enumerate(t.rows):
        for j, cell in enumerate(row.cells):
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tcpr = cell._tc.get_or_add_tcPr()
            shade = OxmlElement("w:shd")
            shade.set(qn("w:fill"), "E8ECF0" if i == 0 else "FFFFFF")
            tcpr.append(shade)
            margins = OxmlElement("w:tcMar")
            for side in ("top", "left", "bottom", "right"):
                v = OxmlElement("w:" + side)
                v.set(qn("w:w"), "100")
                v.set(qn("w:type"), "dxa")
                margins.append(v)
            tcpr.append(margins)
            borders = OxmlElement("w:tcBorders")
            for side in ("top", "left", "bottom", "right"):
                b = OxmlElement("w:" + side)
                for key, value in [("val", "single"), ("sz", "4"), ("color", "D9D9D9")]:
                    b.set(qn("w:" + key), value)
                borders.append(b)
            tcpr.append(borders)
            for para in cell.paragraphs:
                para.paragraph_format.space_after = Pt(3)
                para.paragraph_format.line_spacing = 1.05
                for run in para.runs:
                    run.font.size = Pt(10.5)
                    run.bold = i == 0
    p("")


title = p("TimeBlindAI", "Title")
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
subtitle = p("Implementation and Pilot Evaluation of an Intelligent Time Orchestration System", "Subtitle")
subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
for text in ["", "Aarush Gaur and Aman Sachdeva", "Roll numbers 2023010 and 2023077", "", "BTP report draft for the Degree of BTech", "Computer Science and Engineering", "Engineering Track", "", "BTP Advisor", "Dr Ganesh Bagler", "", "Indraprastha Institute of Information Technology Delhi", "November 2026", "", "DRAFT   Participant results pending collection"]:
    x = p(text)
    x.alignment = WD_ALIGN_PARAGRAPH.CENTER

page("Student Declaration", """
We declare that the work presented in this report, entitled TimeBlindAI, is an authentic account of the project carried out towards the Bachelor of Technology degree in Computer Science and Engineering at Indraprastha Institute of Information Technology Delhi under the guidance of Dr Ganesh Bagler. Sources and prior work must be acknowledged in the final submitted report.

This declaration is a draft for the authors to review. The submitted version must accurately reflect the work completed, the institution's required wording and any reuse of the previous semester's material. No signature or submission is represented by this draft.

Aarush Gaur ____________________     Aman Sachdeva ____________________

Place and date ____________________
""")
page("Certificate", """
The certificate must be reviewed and completed by the project advisor using the institution's required wording after the final report has been checked. This page is intentionally unsigned and does not represent advisor approval.

Project advisor: Dr Ganesh Bagler

Signature ____________________

Place and date ____________________
""")
page("Abstract", """
TimeBlindAI is a web-based productivity assistant for task duration estimation, task decomposition, scheduling, focus sessions and review of recorded outcomes. The previous semester established the conceptual Intelligent Time Orchestration System architecture and a responsive interface. The present phase implements a FastAPI backend, a Next.js frontend, authenticated workspaces, task and session persistence, adaptive scheduling rules, optional Windows activity collection, and administrator exports.

The system combines deterministic temporal reasoning with an optional pretrained language-model integration. Generated task plans and schedule-order proposals are checked by application logic, while a rules fallback supports operation when an external provider is unavailable. This integration is API inference rather than training a language model. Earlier small-scale duration checks did not establish that the model improved on the rules baseline.

An exploratory participant pilot has been designed around prospective predictions and timed everyday tasks. Approximately twenty adults are to be recruited, with three task attempts per participant. The study records a participant's initial guess before revealing an independent rules estimate, followed by server timing, self-reported breaks, completion and scope information, and custom usability feedback. The analysis compares errors on the same eligible completed tasks and reports participant-level averages alongside task-level summaries.

Participant results are pending at the time of this draft. The report therefore distinguishes implemented functionality and saved synthetic checks from unmeasured human outcomes. The final abstract must replace this paragraph with the observed sample size, primary errors, feedback results and a conclusion limited to the pilot evidence.

Keywords: task planning, duration estimation, adaptive scheduling, usability pilot, temporal support, human-centered software.
""")
page("Acknowledgments", """
We thank our project advisor, Dr Ganesh Bagler, for guidance on the project. We also thank participants who voluntarily contribute their time and feedback to the evaluation. The final version should acknowledge only support actually received and should not identify participants without their permission.
""")
page("Work Distribution", """
The project work in this phase covers backend integration, authentication, task and schedule reasoning, focus-session records, optional activity monitoring, administrator exports, evaluation tooling and preparation for participant testing. The final submitted report must distinguish work completed in the previous semester from work completed during the current semester.

Author-specific contributions have not been confirmed for this draft. Before submission, each author should provide the modules, experiments, deployment work and report sections they completed, supported where possible by commits or dated records. This page should be replaced with an accurate joint account rather than an assumed equal division.
""")
table(["Area", "Aarush Gaur", "Aman Sachdeva"], [(a, "To confirm", "To confirm") for a in ["Implementation", "Deployment and testing", "Study administration", "Analysis and report"]], [2.25, 2, 2])

page("Contents")
toc = OxmlElement("w:fldSimple")
toc.set(qn("w:instr"), 'TOC \\o "1-2" \\h \\z \\u')
doc.add_paragraph()._p.append(toc)
p("Update this contents field in Word after final edits. Chapters and appendices follow the academic structure of the previous report.")

page("1 Introduction", """
Planning a task requires a prediction about the time needed to finish it. When that prediction is inaccurate, a schedule can become difficult to follow even if the task list itself is clear. TimeBlindAI addresses this practical problem by connecting the initial plan to recorded execution and subsequent feedback in one application.

The project originated as an Intelligent Time Orchestration System, intended to combine sensing, temporal reasoning, personalization and interventions. Last semester's report concentrated on the conceptual ontology and architectural domains, with a responsive frontend as the initial implementation. This phase develops a working software path through task creation, decomposition, scheduling, timed work and outcome review.

This report separates three types of contribution. The first is engineering: an authenticated web application with persistent task and session records. The second is algorithmic integration: rule-based estimates and scheduling together with an optional language-model interface. The third is evaluation: reproducible synthetic checks and a prospective participant pilot. A functioning feature is not itself evidence that it improves a user's productivity; that distinction determines the evaluation design.
""")
sub("1 1 Scope of the current phase", """
The implemented system assists with planning and collects operational records. The participant study focuses on the usability of this workflow and on agreement between predicted and recorded task durations. It does not diagnose a condition, infer verified cognitive load, or establish that notifications improve attention. Clinical benefits and long-term behavior change are outside the current evaluation.
""")
sub("1 2 Progress since the previous semester", """
The conceptual domains are now represented by application modules and database entities. Tasks, events, sessions, schedule blocks and interventions have concrete records. A Windows companion provides optional foreground-application and inactivity observations. A study-specific entry point adds explicit pilot consent and immutable prediction snapshots. These changes make prospective evaluation possible while retaining the broader architecture as a direction for future development.
""")

page("2 Background and Related Work", """
The previous report reviewed time perception, digital behavioral support, human-centered AI and ontology-based activity representation. These areas motivate the project but do not validate its implementation. The final literature review should make the connection from each source to a particular design decision or evaluation question, rather than repeat broad claims about intelligent assistance.

Research reviewing time perception in ADHD discusses temporal-processing difficulties and variation across studies [1, 2]. These clinical findings motivate caution in terminology: an error in estimating a reading task is not a diagnosis, and a student convenience sample does not represent a clinical population. The present study consequently asks about everyday planning and software use without collecting diagnostic information.

For this phase, the central comparison is deliberately narrow. A participant's prospective guess and a deterministic application estimate are recorded for the same task scope. Recorded work time provides an imperfect outcome measure. This comparison directly tests estimation behavior in the implemented workflow, while custom agreement questions describe the participants' experience of using it.
""")
sub("2 1 Relationship to existing planning tools", """
Calendars and task lists can represent commitments, while timers can record sessions. TimeBlindAI integrates these interactions with task decomposition, schedule revisions and outcome review. The engineering contribution is this connected workflow and its auditable data path. No comparative product trial has been conducted in this phase, so the report does not claim superiority over commercial productivity tools.
""")
sub("2 2 Literature review work still required", """
The final report should retain only references that the authors have checked and used in the text. Add recent task-duration prediction and human-computer interaction evaluation work if it materially informs the analysis. The previous report's unresolved citation must be replaced by a verified source or the associated unsupported claim must be removed. The current bibliography is a starting set rather than a complete literature survey.
""")

page("3 Problem Statement and Objectives", """
The engineering problem is to connect a user's task intention to a feasible plan and an interpretable record of what happened. The evaluation problem is to measure this workflow without treating generated advice, synthetic behavior or retrospective guesses as observed evidence of human improvement.

The current objectives are to implement authenticated end-to-end task planning and session recording; maintain a deterministic scheduling and fallback path; expose optional generative planning with provenance; collect prospective paired estimates and timed outcomes; and document usability problems and evidence limits.
""")
table(["Question", "Evidence", "Interpretation"], [
    ("Can people complete the flow?", "Enrollment, starts, completions and feedback counts", "Feasibility within the recruited sample"),
    ("How accurate are the estimates?", "Paired human and rules error on identical eligible tasks", "In-use descriptive accuracy"),
    ("How do participants experience the app?", "Five custom ratings and optional comments", "Perceived usability and usefulness"),
], [1.8, 2.4, 2.05])
sub("3 1 Evaluation boundaries", """
Approximately twenty participants and sixty task attempts are recruitment targets. The study is not powered to demonstrate a clinical outcome or a causal increase in productivity. An initial usability pilot remains useful if fewer people finish; the report must show recruitment and attrition rather than substitute planned counts for observed ones.
""")

page("4 Architecture and Ontology Mapping", """
The application uses a Next.js and React frontend with a FastAPI backend. SQLAlchemy provides persistent domain records, using SQLite by default and supporting a configured PostgreSQL deployment. The frontend proxies API requests to the backend, allowing the browser to use the same origin for authenticated requests. Server-side ownership checks restrict access to each user's workspace.

The ontology remains a conceptual description of the domain. In this implementation, it is reflected in typed schemas, database relationships and module boundaries. The presence of entities such as attention state does not establish a validated latent-state estimator. A separate formal ontology reasoner is not claimed by this report.
""")
table(["Conceptual domain", "Implemented mechanism", "Current limit"], [
    ("Interaction", "Task, schedule, focus, review and study pages", "Usability requires participant evidence"),
    ("Sensing", "Optional Windows app and idle intervals", "Not ground truth for attention"),
    ("Time intelligence", "Duration rules and block timing", "Heuristic prediction"),
    ("Decision and intervention", "Greedy scheduling, replanning and rule-based reminders", "No measured causal benefit"),
    ("Personalization", "Historical duration adjustments in the main app", "Pilot freezes unpersonalized rules"),
    ("Learning", "Export and offline evaluation tooling", "No online model training claim"),
], [1.45, 2.8, 2])
sub("4 1 Data flow", """
The participant authenticates, accepts study information and supplies task scope and an initial estimate. The study endpoint independently computes a rules estimate and saves both values before responding. Starting work records a server timestamp and a linked session. Finishing work saves elapsed time, reported breaks, outcome and scope status. An administrator can then inspect consent-filtered aggregates and export pseudonymous tables. The study record remains separate from ordinary editable task fields so later task edits do not rewrite the prospective comparison.
""")

page("5 Implementation", """
The main application provides user registration and password login, authenticated workspaces, task decomposition, event preparation, scheduling, focus sessions, post-session feedback and review insights. Administrator routes require an explicit grant, and exported operational datasets omit credential tables. The newest participant flow builds on these foundations rather than introducing a separate data collection service.
""")
sub("5 1 Duration estimation and generative planning", """
The deterministic decomposer uses task characteristics and programmed rules to derive a duration and steps. The main app also supports historical adjustments. An optional language-model integration uses Groq or OpenAI to propose task estimates and decomposition, and to propose schedule ordering. The backend checks structured outputs and can fall back to rules. This is inference with a pretrained provider model, not training or fine-tuning a language model on the project's small dataset.

The participant study uses a separate frozen configuration: deterministic decomposition, multiplier 1.0, no supplied starting estimate and no external provider call. This prevents the participant's own guess from mechanically influencing the comparator and avoids provider reliability becoming a hidden source of missing study records. The comparison does not evaluate the main app's personalized method or the LLM.
""")
sub("5 2 Scheduling and interventions", """
Schedules place work around time windows, events and dependencies, using a greedy heuristic with risk buffers. Replanning retains relevant ongoing and completed work and records revisions. Reminders respond to programmed signals including overdue work, switching bursts and observed inactivity. These are operational proxies. Idle input can reflect reading or thinking, and switching applications can be relevant work.

The previous report's estimate-relative deviation is actual duration minus estimate, divided by estimate. The live overdue reminder policy uses minutes past a block's end divided by planned duration. The two ratios refer to different events and must not be presented as the same measure or as a clinical timeblindness score.
""")
sub("5 3 Study collection and administration", """
The /study page contains participant information, consent, task entry, timing and final feedback. The /study/admin page displays counts and paired error summaries. Study tables store enrollment, prediction and outcome snapshots, and feedback. Withdrawn participation is excluded from the dedicated study summary, comments and export. The raw operational database remains private until deletion by the project team.
""")

page("6 Evaluation Methodology", """
We propose a short prospective pilot with approximately twenty adult volunteers recruited through the project team's peers. Each participant is asked to attempt three naturally occurring tasks over two days. Two separate practice accounts should first exercise the entire hosted workflow and then be withdrawn from analysis. Recruitment is a convenience sample, and no random assignment or clinical screening is planned.
""")
sub("6 1 Task procedure", """
Participants select tasks that have not yet started, define a clear finish point and enter task category, difficulty and an initial duration guess. The application saves that guess and a separate rules estimate before revealing the latter. Participants inspect the plan, may try the scheduler, and use the study timer while working. They report breaks and unrelated work at the end, specify whether the original scope was completed and indicate scope changes. A forgotten or unreliable timer is marked unfinished rather than treated as a valid duration observation.

The target task scope is usually fifteen to sixty minutes, with longer work divided into concrete units. The study does not require participants to manufacture tasks to reach a quota. Participants who stop early can still provide feedback after an attempted task. The app estimate is visible during use and may influence pace; the resulting comparison is therefore not blinded.
""")
sub("6 2 Outcomes and exclusions", """
Recorded work time equals server elapsed time minus self-reported breaks. A task enters the paired accuracy analysis only if the participant still consents, the task was completed, scope did not change and recorded work time is at least one minute. Scope changes, unfinished attempts and missing outcomes are counted separately. Both prediction methods use exactly the same eligible rows.

Primary descriptive accuracy is mean absolute error in minutes. We also report median absolute error and the percentage of tasks whose error is at most fifteen minutes. To avoid allowing participants with more records to dominate the summary, we compute each participant's mean error and average these participant means. The number of participants is reported separately from the number of tasks.
""")
sub("6 3 Feedback and safeguards", """
Five custom agreement questions measure ease, clarity, usefulness, trust and willingness to use the app again. Each item's median and five-category distribution are reported separately. These items are not the System Usability Scale and are not converted to a standardized score. Optional comments are coded into descriptive themes after removal of identifying information.

Consent covers data use, withdrawal and proposed deletion by December 25, 2026. Confirm institutional requirements with the supervisor before recruitment. No diagnosis is collected or ethics approval asserted.
""")

page("7 Results", """
This chapter distinguishes saved pre-pilot engineering evidence from the participant study. Human outcomes have not yet been collected for this draft. Recruitment targets must not be substituted for measured counts, and a successful build must not be described as successful deployment or user validation.
""")
sub("7 1 Existing synthetic checks", """
The repository's saved synthetic benchmark reports 300 duration records over fifteen simulated profiles and 146 of 146 specified policy and scheduler checks passing. On sixty records from held-out simulated profiles, rules MAE was 40.05 minutes and train-calibrated rules MAE was 25.81 minutes [3]. These values measure behavior under the generator's assumptions. They provide reproducible software evidence but do not establish an improvement for human users.

The README records a six-task unseeded generative-duration pilot with three valid AI responses and no improvement over rules [4]. This is integration and reliability evidence from an earlier small experiment, not a result of the November participant study. The original provider configuration and evaluation files should accompany any detailed comparison.
""")
sub("7 2 November participant cohort", """
Pending collection and cutoff review. Enter actual observed counts below. Keep a dated private audit of exclusions and withdrawals. If fewer than the target number participate, report the smaller sample and explain the practical limitation.
""")
table(["Measure", "Observed value"], [(a, "Pending pilot") for a in ["People invited", "Consenting participants at cutoff", "Started tasks", "Completed tasks", "Unfinished and active tasks", "Eligible paired-duration records", "Feedback responses"]], [4.25, 2])
sub("7 3 Prediction and feedback findings", """
Pending collection. Insert the paired human-versus-rules error table, participant-level paired plot, actual-versus-predicted scatter and rating distributions after validating the export. Include sample size, units and denominator on every table or figure. Describe inaccurate predictions and negative feedback with the same care as favorable results.
""")

page("8 Discussion and Limitations", """
The implemented system makes planning decisions and their recorded outcomes observable within a connected workflow. This is the principal engineering advance over the previous semester's conceptual architecture. The participant pilot is intended to reveal whether users can complete that workflow and whether the estimates are useful enough to justify further refinement.

Interpretation is limited by convenience sampling, a short collection window, task diversity and repeated observations from the same people. Friends of the project team may provide more favorable feedback. Participants choose their own tasks, and scope can be difficult to express consistently. Break durations are self-reported; the server clock does not distinguish focused work from unrelated activity. A visible prediction may influence the outcome it is compared with.

The pilot compares human guesses with one frozen rules method. It provides no randomized baseline condition for productivity gains, no long-term personalization trial and no causal estimate of reminder effectiveness. The optional Windows companion is not required and is outside the participant study; clinical state inference and distraction classification remain unvalidated. The five feedback questions are custom items with descriptive interpretation.

Prior offline modeling also requires caution. Features such as the number of sessions eventually completed for a target task are unavailable when that task is first predicted. Such post-task features cannot support a prospective accuracy claim. New comparisons should use only information available before work starts, maintain a frozen evaluation set and keep synthetic data separate from consented human records.
""")
sub("8 1 Interpretation after collection", """
The final discussion should explain the direction and variation of observed errors, which parts of the workflow participants found difficult, and which changes the evidence supports. If rules estimates are worse than human estimates, that remains a useful result: it identifies the need for better task-scope inputs and future calibration. A small or inconclusive pilot should lead to a restrained conclusion rather than an invented improvement percentage.
""")

page("9 Future Work", """
The immediate next step after the pilot is to address recurring usability and reliability problems identified by participants. Changes to consent or timing should be distinguished from changes to prediction behavior, and a new protocol version should be used for a materially different experiment.

A larger prospective dataset could support calibration using historical tasks completed before each new prediction. Evaluation should preserve participant grouping and time order, and avoid training on the same tasks used to report performance. Task-scope descriptions and quantity units deserve particular attention because a task category alone cannot determine a person's workload.

The optional language-model method requires a separate paired evaluation with provider failure rates, successful-call accuracy and full-policy accuracy including fallback. Schedule quality should be tested under identical task durations, windows, events and dependencies, with explicit hard-constraint checks. Reminder benefit would require a comparison design that measures outcomes beyond whether a programmed rule fired.

Longer-term work can study sustained use, participant control over reminders, deployment reliability and more accessible interactions. Clinical claims would require a different evaluation scope and appropriate expertise. The current engineering system provides a platform for such work, while the November pilot remains a limited first observation of everyday use.
""")

page("10 Conclusion", """
TimeBlindAI has progressed from a conceptual Intelligent Time Orchestration System and responsive interface to an integrated application with authenticated task planning, scheduling, sessions, feedback, optional activity monitoring and administrator data access. Deterministic logic supplies a verifiable baseline, while optional generative planning extends the system without establishing superior predictive accuracy.

The November evaluation design connects prospective human and rules estimates to recorded outcomes and custom usability feedback. Separate study snapshots, consent filtering and explicit eligibility rules support an auditable analysis. These mechanisms address the need for measurable evidence without confusing synthetic checks with participant outcomes.

Participant findings remain pending in this draft. The submitted conclusion must state the actual cohort, the main accuracy and feedback findings and the limits of the evidence. Until those observations exist, the supported contribution is the implementation and the evaluation protocol, rather than a claim that the system improves productivity or timeblindness.
""")

page("Bibliography")
for reference in [
    "[1] R. Ptacek et al., Clinical Implications of the Perception of Time in Attention Deficit Hyperactivity Disorder (ADHD): A Review, Medical Science Monitor, 25, 3918-3924, 2019. https://pmc.ncbi.nlm.nih.gov/articles/PMC6556068/",
    "[2] C. Mette, Time Perception in Adult ADHD: Findings from a Decade-A Review, International Journal of Environmental Research and Public Health, 20(4), 3098, 2023. https://doi.org/10.3390/ijerph20043098",
    "[3] TimeBlindAI repository, data/evaluation/synthetic/report.md and docs/synthetic-evaluation.md, saved synthetic benchmark, inspected November 21, 2026. Record the final deployed commit before submission.",
    "[4] TimeBlindAI repository, README.md, docs/llm-integration.md and data/evaluation/groq_live_unseeded.json, generative integration and earlier evaluation records, inspected November 21, 2026.",
    "[5] Aarush Gaur and Aman Sachdeva, TimeBlind-AI: Intelligent Time Orchestration System (ITOS), prior-semester BTP report, IIIT Delhi, April 21, 2026. Supplied project report.",
    "[6] TimeBlindAI repository, docs/pilot-study.md, November participant protocol, version nov2026-pilot-v1. Proposed collection November 22-23, 2026.",
]:
    p(reference)

page("Appendix A Participant Questionnaire", """
Study entry asks participants to confirm that they are at least eighteen years old and that they have read the study information and voluntarily consent to participate. The information identifies the project team, purpose, task procedure, collected data, account linkage, withdrawal route, deletion plan and contact address.

The baseline question asks how often tasks take longer than initially expected, with never, rarely, sometimes, often and very often as options. This item describes the sample and has no diagnostic interpretation.

For each task, participants enter a concrete title, category, difficulty and personal duration estimate before seeing the app prediction. At the end they report completion or unfinished work, break minutes, scope changes and the main friction reason.
""")
for statement in ["The app was easy to use.", "The task plan was clear.", "The app helped me plan my work.", "I could rely on the time estimates.", "I would use this app again."]:
    p(statement, "List Bullet")
p("Each item uses 1 strongly disagree, 2 disagree, 3 neutral, 4 agree and 5 strongly agree. Optional written prompts ask what helped most, what the biggest problem was and what should be improved first. These are custom items, not SUS.")

page("Appendix B Analysis and Submission Checklist", """
Freeze the protocol and deployed commit before recruitment. Practice accounts must be separate and excluded. Record the actual collection window and export timestamp. At the cutoff, reconcile enrolled, withdrawn, started, completed, unfinished, active and feedback counts.

Include only consented, non-withdrawn, completed tasks with unchanged scope and at least one recorded work minute in paired duration accuracy. Preserve raw elapsed and break minutes. Use identical rows for both predictions. Report both participant N and task N. Do not treat repeated tasks as independent people.

After collection, replace all pending-result fields, add observed figures and current screenshots, revise the abstract and conclusion, confirm author contributions, update the contents, check references and page numbering, and obtain the actual declaration signatures and advisor certification. The final report should clearly identify which work belongs to this semester.

Keep identifiable account data and pilot exports out of the public repository. Remove private details before quoting feedback. Confirm that withdrawal is reflected in the working analysis and that the proposed retention commitment can be met. Report deployment verification separately from local tests.
""")

from pilot_report_details import add_details
add_details(page, sub, p, table)

doc.core_properties.title = "TimeBlindAI Implementation and Pilot Evaluation Draft"
doc.core_properties.author = "Aarush Gaur and Aman Sachdeva"
doc.core_properties.subject = "November 2026 BTP draft with participant results pending"
doc.save(OUT / "TimeBlindAI_BTP_November_Draft.docx")
print(OUT / "TimeBlindAI_BTP_November_Draft.docx")
