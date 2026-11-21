"""Update the draft to the guided AI protocol without inventing human results."""
def revise(doc, page, sub, p, table):
    replacements = {
        "An exploratory participant pilot has been designed": "An exploratory participant pilot uses the original application through a guided study entry point. Participants receive genuine LLM task plans, use the original focus workspace and create saved AI-assisted schedules. Their own guesses and an independent rules baseline are retained before work starts. Each attempted task records its timing source, scope status and a short plan review. A separate scheduler review asks about feasibility, ordering and guidance. Human outcome results remain pending.",
        "For this phase, the central comparison": "The evaluation compares prospective human, rules and LLM duration predictions on eligible live-timed tasks with matching scope. The AI-success cohort and failed requests are reported explicitly. Manual recalled times and hypothetical rehearsals remain separate. Per-task ratings and scheduler reviews describe perceived usefulness; recorded execution of saved schedules supplies a distinct adherence measure.",
        "The participant study uses a separate frozen configuration": "The guided AI pilot requires a successful LLM response for each new task plan and saved schedule. It uses the same task estimator and scheduling route as the main application. Python still checks output structure and places feasible blocks. AI outages produce a visible failure, not a rules plan presented as AI. An independent unpersonalized rules estimate remains a comparator, and provider/model/prompt provenance is saved.",
        "The study endpoint always": "New study plans require AI; legacy rules-only records are retained with their original method label.",
        "The deterministic decomposer uses": "The deterministic decomposer supplies a comparison baseline from task characteristics. The main app supports historical adjustments and optional pretrained-model calls. In the guided AI pilot the latter is required for new plans: estimates, steps, assumptions and explanations are returned by the provider and validated by the backend. Structured output validation does not prove duration accuracy.",
        "The task form records": "The task form records concrete scope, context, difficulty and a personal guess before revealing an AI plan. A separate rules estimate is computed without the personal guess.",
        "The participant authenticates, accepts": "After authentication and study enrollment, participants explicitly confirm the AI data-use information. Task descriptions and limited completed-task history may reach the configured provider; optional desktop activity is not included in these planning prompts. Plans and steps are saved as ordinary tasks. Starting work creates a shared session that the original focus workspace can resume. Its pilot completion action returns to the guided outcome and review form, preserving one timer and one study record.",
        "The participant study focuses": "The participant study focuses on the usability of the actual application, duration estimation and AI-assisted scheduling. It does not diagnose a condition or establish a clinical benefit.",
        "The main app also supports historical": "The main app supports historical calibration and pretrained AI inference. The November AI pilot tests that integration with explicit provider provenance and a separate rules baseline.",
        "For each task, participants enter": "For each task, participants enter concrete scope, context, category, difficulty and their own duration guess before seeing the AI prediction. Outcomes record work-time source, completion, scope changes, friction, plan helpfulness, estimate reasonableness and optional comments.",
        "Participants select tasks that have not yet started": "For duration evaluation, participants select unstarted work with a clear completion condition. The application records the initial guess, independent rules estimate and AI plan before revealing the result. Participants use the original focus workspace or its shared study timer, then return to the guided form to report breaks, completion, scope changes and per-task feedback. Recalled or hypothetical manual values support a quick interface rehearsal but are excluded from prospective accuracy.",
        "The pilot compares human guesses with one frozen rules method": "The pilot now compares AI estimates against human guesses and independent rules where matching live outcomes exist. Historical rules-only pilot records remain separate. A guided path through the actual task and scheduling APIs replaces the earlier hypothetical scheduler exercise. There is still no randomized condition establishing causal productivity gains, clinical benefit or long-term personalization.",
        "The participant study uses a separate": "The current guided study uses the application's AI pipeline and records its provenance, retaining deterministic rules as a baseline rather than as the participant-facing AI plan.",
    }
    for paragraph in doc.paragraphs:
        text = paragraph.text
        for prefix, replacement in replacements.items():
            if text.startswith(prefix):
                paragraph.text = replacement
                break
        else:
            if "The pilot deliberately" in text or "The study deliberately fixes" in text:
                paragraph.text = "Category defaults and historical calibration remain deterministic comparison mechanisms. New guided plans require successful LLM output. The independent rules comparator omits the personal guess, while AI receives task scope and limited historical outcomes. Separate method labels prevent older rules records from being mistaken for AI results."
            elif "does not evaluate personalized learning, an LLM" in text:
                paragraph.text = "The current evaluation includes genuine LLM inference and AI-assisted scheduling, with no claim of model training. Provider reliability, paired prediction error, per-task feedback and recorded schedule execution are distinct outcomes."
    for table_obj in doc.tables:
        for row in table_obj.rows:
            for cell in row.cells:
                if "Pilot freezes unpersonalized rules" in cell.text:
                    cell.text = "AI required; rules retained as comparator"
                if "Paired human and rules error" in cell.text:
                    cell.text = cell.text.replace("Paired human and rules error", "Paired human, rules and AI error")
    for paragraph in doc.paragraphs:
        if "The November evaluation design connects prospective human and rules estimates" in paragraph.text:
            paragraph.text = paragraph.text.replace("The November evaluation design connects prospective human and rules estimates", "The November evaluation design connects prospective human, independent rules and AI estimates")
    page("Appendix I Guided AI Pilot Revision", """
The revised workflow is a guided study mode for the original application. It does not substitute a generic scheduler for the project implementation. AI task plans are persisted as ordinary tasks and steps. The original focus workspace resumes the same active session; pilot completion returns to the task review form. The scheduling exercise now creates actual upcoming tasks and calls the original schedule generation route with AI required. Participants can open scheduled focus blocks directly and review the saved plan afterwards.

AI-assisted scheduling is a hybrid implementation. A pretrained LLM proposes task order and explains its ordering; Python places work and enforces time windows, deadlines, dependencies, events and breaks. This is not model training or an unconstrained LLM calendar. The application does not return a rules schedule as a successful AI trial if the provider is disabled or unavailable.
""")
    sub("I 1 Scope changes and per task reviews", """
Scope means the amount and finish condition of the work being estimated. Estimating five pages but completing ten changes scope. Taking longer to complete the original five pages does not. Scope-changed tasks are retained in the participation accounting and excluded from paired duration error. Every guided task's completion form asks whether the plan helped and whether the estimate seemed reasonable, using separate five-point ratings, alongside friction and optional written comments.

Three timing modes are explicit: live timer, recalled real duration and hypothetical rehearsal. Neither manual mode enters primary prospective duration accuracy. Rehearsal values do not become ordinary task duration-training targets. Real accuracy still requires doing real work; allowing immediate manual entry cannot create a measured human outcome.
""")
    sub("I 2 Current integration evidence", """
A live Groq scheduler ordering request using isolated synthetic inputs returned a valid LLM ordering. An initial task request failed provider-side JSON validation because the generated response exceeded the permitted step count. The task prompt was revised to prefer three to six useful steps, cap the count at twelve and check duration consistency. A subsequent live request to openai/gpt-oss-120b returned a 45-minute plan with five steps whose durations summed correctly. The revised task prompt is timeblind-v2.

These are local integration observations, not participant results or a reliability-rate estimate. The initial failure must not be erased from the account of the check. Controlled regression tests use mocked provider output and cannot establish live provider accuracy. Render configuration and a complete hosted participant journey remain to be verified after deployment.
""")
    sub("I 3 Measures and interpretation", """
Task accuracy uses prospective completed tasks with unchanged scope and valid live timing. Report human and rules results on their eligible cohort, and AI results with its explicit successful-plan sample size. The report-safe export records AI estimate values, model and prompt identifiers, per-task rating values and AI-attempt success/failure. Free text and task descriptions are omitted from that export.

Scheduler constraint conformance is the percentage of saved plans passing the specified checks. Perceived usefulness is the share of reviews rating guidance four or five, with numerator and denominator. Recorded schedule adherence compares completed nonmanual blocks with their planned end times; original snapshots remain distinguishable from later schedule revisions. Manual-duration sessions are labeled and excluded from that execution measure. Hypothetical inspection alone does not supply adherence evidence.

The admin summary separately reports planned task blocks, completed nonmanual blocks, completion by planned end, manual exclusions and missing or replaced blocks. Missing execution must not be counted as a successful completion or hidden by reporting only those who finished. These records depend on participants honestly starting and ending sessions; they do not independently verify attention.
""")
    sub("I 4 Deployment and remaining evidence", """
Configure the Render backend with persistent DATABASE_URL, LLM_ENABLED=true, the selected LLM_PROVIDER and LLM_MODEL, a private provider key, and LLM_FAILURE_MODE=error for the AI pilot. Keep provider secrets on the backend. Restart or redeploy both services from the same source revision and verify a complete hosted journey before invitations. Existing participants must confirm the updated AI data-use information before new study provider calls.

No participant sample, accuracy percentage or productivity benefit is manufactured in this draft. The final report requires the observed cohort and dates, provider attempts and failures, valid paired durations, per-task ratings, scheduler reviews and any measured execution. It also requires verified author contributions, current interface screenshots, final reference checks and actual signatures.
""")
