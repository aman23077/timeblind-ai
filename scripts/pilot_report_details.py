"""Detailed technical appendices for the November BTP draft."""
def add_details(page, sub, p, table):
    page("Appendix C Data Model and API Design", """
The persistent model separates planned work from recorded execution. A user owns tasks, events, schedules and sessions. Task steps belong to a task and carry their order and suggested duration. Dependencies express prerequisites between tasks. A schedule groups time blocks for a date, and blocks can refer to tasks or reserved events. A session can be linked to both a task and a block, allowing planned and observed timing to be compared.

This separation matters when a plan changes. A task is a description of work; a time block is an allocation; a session is an observation of execution. Treating them as the same object would make it difficult to distinguish an inaccurate estimate from a late start or a rescheduled commitment. Plan revisions preserve changes instead of replacing every earlier state without an audit trail.
""")
    table(["Entity", "Important fields", "Purpose"], [
        ("User", "Time zone, preferences, research consent", "Workspace and preferences"),
        ("Task", "Type, difficulty, quantity, estimate, actual, deadline", "Scope and duration outcome"),
        ("TaskStep", "Order, suggested minutes, rationale", "Actionable decomposition"),
        ("TimeBlock", "Start, end, status, buffer, risk", "Calendar allocation"),
        ("SessionRecord", "Start, end, elapsed, feedback, task link", "Observed session"),
        ("PlanRevision", "Schedule link and previous allocations", "Replanning history"),
        ("ActivityInterval", "Monitor, executable, state and times", "Optional device observations"),
        ("StudyTask", "Original paired estimates and final outcome", "Prospective study snapshot"),
    ], [1.2, 3, 2.05])
    sub("C 1 Request validation and resource ownership", """
Pydantic schemas validate structured requests, including supported task types, difficulty values and numeric limits. Workspace authorization checks resource references against the authenticated user before operations proceed. Study routes derive the enrollment from the logged-in user and resolve each study record through that enrollment. Administrator operations require an explicit grant rather than relying on a hidden page or an email string displayed in the interface.

Task creation and decomposition are distinct operations in the main application. Decomposition proposes a plan; creation persists the task, and step endpoints save the generated steps. The study path saves its own independent estimate snapshot together with the ordinary task and steps. It does not trust a client-supplied rules prediction or accept a client-supplied completion timestamp.
""")
    sub("C 2 Study state transitions", """
A study task begins in planned state. Starting it records server time and creates a linked session, moving it to active state. A finished record becomes completed or unfinished. Predictions cannot be patched through the study API, and a second finish request is rejected. A database constraint permits only one active study task per enrollment. This reduces overlapping timers and protects against accidental duplicate starts.

Enrollment retains its protocol and withdrawal timestamp. Withdrawal excludes records from study analysis; deletion requires separate removal of private records and working copies.
""")
    page("Appendix D Reasoning and Scheduling Details", """
The rules decomposer uses a base duration by task category, difficulty multipliers and task-specific quantity rules. Text keywords also help select an interpretation. The category baselines in the inspected code include 60 minutes for assignments, 35 for reading, 50 for study, 55 for writing and 65 for coding. Easy, medium and hard difficulty use multipliers of 0.85, 1.0 and 1.25. These are programmed defaults, not parameters learned from the November participant cohort.

The main application can adjust duration using historical actual-to-estimate ratios and session feedback. Its historical adjustment is smoothed towards a prior and bounded rather than allowed to grow arbitrarily from a single unusual task. The study deliberately fixes the multiplier at 1.0. Consequently, its results must be described as an evaluation of the unpersonalized rules comparator, not the complete personalized system.
""")
    sub("D 1 Feasibility and task decomposition", """
The decomposer returns a total estimate, steps, confidence label, urgency and a fit assessment where applicable. The fit assessment compares available time with predicted work. It can report that a task fits, is tight or overflows the available window. An approaching deadline does not justify reducing the required work solely to make the calendar look feasible.

Steps make a high-level goal easier to act on, but their proposed minutes are still estimates. The system should communicate assumptions and allow task scope to be clarified. A confidence label from rules is a heuristic communication device; it is not a measured probability that the task will finish within the proposed time.
""")
    sub("D 2 Generative inference and validation", """
The optional provider receives task details and a bounded selection of historical examples. It is asked to return structured predictions, steps and explanations. The backend validates schema and cross-field consistency, including duration ranges and step sums. A valid JSON response can still be inaccurate, so formatting reliability and predictive accuracy are evaluated separately.

For schedule generation, the language model may propose task ordering. Python retains responsibility for calendar placement and constraint checks. External inference can fail through network errors, exhausted provider quota, invalid structure or inconsistent outputs. The application records provenance and can return a rules fallback. A fallback is not counted as a successful language-model response in evaluation.
""")
    sub("D 3 Adaptive replanning", """
The scheduling logic considers deadlines, priority, task duration, dependencies, fixed events and available time. It selects feasible work with a greedy procedure and records tasks that cannot fit. An active session reserves forecast completion time rather than being ignored when the remaining day is replanned. Updated remaining-time reports allow the forecast to change while preserving ongoing work.

Policy evaluation is limited to at most once every thirty seconds per user while the application or companion is operating. Replanning can respond to task changes, reservations, remaining-time updates and time progression. This behavior is a heuristic adaptation mechanism; the repository does not establish that it finds a globally optimal schedule or improves completion rates for users.
""")
    sub("D 4 Intervention rules", """
The documented initial policy prioritizes slippage, late starts, switching, idle observations and upcoming work in that order. Slippage prompts require at least five overdue minutes and an overdue-to-planned-duration ratio of at least 0.20. A sustained-switch signal requires sufficient recent coverage and sustained active runs; a burst of four switches within five minutes can trigger the switching rule. The input-idle rule requires at least 120 observed idle seconds. Ten-minute global cooldowns reduce repeated prompts, with a longer twenty-minute interval for minimal reminders.

These thresholds encode the design's starting behavior and should be reported as configuration rather than empirical discoveries. Observations must be fresh; missing observation time is not treated as idle time. The participant pilot does not experimentally isolate these reminders, and their presence cannot support an effectiveness claim.
""")
    page("Appendix E Authentication Monitoring and Deployment", """
The application stores salted password hashes using PBKDF2 with SHA-256 and 600,000 iterations. Login uses opaque session tokens whose hashes are stored server-side. Cookies are HTTP-only, use SameSite protection and become Secure in the configured production environment. Authentication has rate limiting, and browser mutations require a request-protection header with origin checking. These mechanisms reduce specific access risks; they do not constitute an independent security audit.

The account recovery mechanism is an operator capability. A universal recovery key can reset accounts, so it must remain private and must never be included in the report, repository or participant materials. Account emails, passwords, cookies, pairing tokens and private provider keys are omitted from this draft and from research exports.
""")
    sub("E 1 What Windows monitoring measures", """
The optional Windows companion samples foreground application and input inactivity approximately every two seconds. It sends executable basenames and bounded timestamp intervals. Full executable paths are discarded locally. After sixty seconds without input, new observations are classified as idle. Suspend gaps and unavailable processes are handled as missing or unknown observations rather than confidently labeled behavior.

Browser tabs share one executable identity, as do windows of the same application. Very short switches can be missed. Reading and thinking can create input inactivity. The companion therefore measures device interaction patterns, not ground-truth distraction, cognitive load or task progress. Pairing tokens are scoped to a session, stored as hashes and revoked when collection ends. Monitoring is optional and not required in the November pilot.
""")
    sub("E 2 Deployment requirements", """
The existing deployment uses separate frontend and backend services. Both should run the same reviewed source revision. Frontend API rewrites depend on the configured backend URL at build time. The backend requires its persistent database URL and the allowed frontend origin. Local build success establishes that the source can compile; it does not establish that these hosted settings or account grants are correct.

SQLite on an ephemeral filesystem can lose records during service restarts or redeployment. The pilot requires either an existing persistent database service or a correctly mounted persistent disk. Before recruitment, create test records, redeploy normally and confirm those records remain. Verify signed-out and non-admin rejection, data export, ownership isolation and the workflow on desktop and mobile. Hosted persistence verification remains pending in this draft.
""")
    page("Appendix F Dataset Audit and Historical Experiments", """
The inspected historical CSV contains 47 rows and seven user identifiers. The stricter audit in the saved generative evaluation retains 28 unique completed records after checking status, duration bounds and conservative duplicates. Records that are incomplete or duplicated must not be quietly treated as independent supervised observations. Existing account provenance and research consent must also be checked before reuse.

The latest twenty percent of the eligible sequence supplied six held-out rows, leaving twenty-two earlier records. Those earlier records were not a language-model training set: no provider weights were updated. The saved artifact labels the evaluation zero-shot-v1 and omits stored estimates from model inputs. Completion timestamps were unavailable in this CSV, limiting use of trustworthy historical examples.
""")
    table(["Saved experiment", "Reported result", "Interpretation limit"], [
        ("Earlier linear regression", "31 supervised rows; 24 train and 7 test; MAE 29.27 min versus raw 43.00 min", "Different selection and split; potential post-task feature leakage"),
        ("Unseeded Groq duration evaluation", "6 attempted tasks; 3 valid responses; 50% failure; successful-call MAE 202 min", "Small retrospective pilot; successes are a selected subset"),
        ("Rules on same AI-success subset", "MAE 33 min on the same 3 tasks", "Paired subset comparison only"),
        ("Synthetic held-out profiles", "60 test records; rules 40.05 min; calibrated rules 25.81 min MAE", "Generator-dependent simulation"),
    ], [1.5, 2.9, 1.85])
    sub("F 1 Why sample matching matters", """
The unseeded artifact reports rules MAE of 49 minutes over all six holdout tasks, while language-model MAE of 202 minutes is calculated over only three successful responses. Those numbers have different denominators. The project's earlier analysis records rules MAE of 33 minutes on those same three successes, which is the appropriate subset comparison. Failures must still be reported to describe the full AI-enabled policy. A success-only score hides reliability costs.

The saved model-generated range coverage is zero on the successful subset, and mean reported call latency is approximately 2.26 seconds. Neither result should be generalized beyond that small saved experiment. The range is not a calibrated confidence interval, and fast responses do not imply useful predictions.
""")
    sub("F 2 Leakage and historical model artifacts", """
The earlier regression features include completed_session_count. For a task being predicted before it starts, the final count is not yet known. Using this eventual outcome as an input can leak future information into evaluation. Its saved improvement is therefore a proof of the training pipeline, not a clean demonstration of prospective performance.

The runtime inspected for the project explanation does not load the saved linear model artifact into normal task estimation. The report must distinguish a research script from an integrated product feature. The November pilot does not train a replacement model and then report performance on its own training observations.
""")
    page("Appendix G Verification and Reproducibility", """
During preparation of the study implementation on November 21, 2026, the backend suite completed with 104 tests passing. The production frontend build also completed and generated the study and study-administration pages. These are local engineering checks. The test output included dependency deprecation warnings; a passing suite does not establish deployment reliability, penetration resistance or human usability.

Study-specific tests cover explicit consent, rejection of unauthorized access, ownership isolation, independence of the rules prediction from the user's guess, one active task per member, invalid break durations, repeated starts and finishes, scope-change exclusions, feedback distributions, export privacy and withdrawal filtering. These checks exercise the data collection contract using controlled test records.
""")
    table(["Evidence", "Status in this draft", "Required next action"], [
        ("Backend tests", "104 passed locally", "Record final tested revision"),
        ("Frontend production build", "Passed locally", "Deploy matching frontend revision"),
        ("Synthetic checks", "Saved report states 146/146", "Retain generator and seed"),
        ("Hosted persistence", "Not verified for new study deployment", "Create record and redeploy"),
        ("Participant outcomes", "Not yet collected", "Complete prospective pilot"),
        ("Author contribution statement", "Not confirmed", "Both authors review and supply details"),
    ], [1.6, 2.25, 2.4])
    sub("G 1 Reproduction record", """
Record the source commit, operating environment, Python and Node versions, deployed database type, configuration, collection cutoff and export timestamp. Keep credentials out of that record. For saved synthetic results, retain seed 23077 and distinguish simulated profiles from real participants. Freeze prediction behavior throughout collection, or document a new protocol version and analyze versions separately.

Retain an untouched private export and a separate analysis copy. Every exclusion should have a reason and should be applied identically to both methods. At submission, confirm that the cohort still excludes withdrawn participants. Reproducibility requires the same input cohort and computation rules, not only a chart image.
""")
    page("Appendix H Detailed Analysis Plan", """
For each eligible task, subtract actual work minutes from the prediction and take the absolute value. Average those values to obtain task-weighted mean absolute error. Sort them to calculate median absolute error. Count errors of fifteen minutes or less and divide by the number of eligible tasks to obtain the within-fifteen-minute percentage. Use the same records for human and rules estimates.

For the participant-weighted comparison, calculate each person's mean error separately for each method and average those person-level means. Plot the paired values for each participant. The count of people contributing to this plot can be smaller than the total enrolled count if some participants have no eligible completed tasks. Report both counts explicitly.
""")
    sub("H 1 Planned tables and figures", """
The participant-flow table should show invited people, enrollments, withdrawals and the analysis cohort. A task-accounting table should show planned, active, completed and unfinished records, plus completed records excluded for changed scope or insufficient valid duration. The primary prediction table should report identical task N and participant N, mean error, median error, within-fifteen-minute percentage and mean participant error.

Recommended figures are paired participant-error points, an actual-versus-predicted scatter plot and a stacked distribution for each custom rating. Use minutes on numeric axes and label all denominators. Do not draw an improvement chart from target counts or fill pending figures with simulated participant responses. Synthetic plots belong in a separately identified experiment.
""")
    sub("H 2 Qualitative feedback and negative results", """
Read all optional responses before defining a short codebook. Possible categories include unclear task scope, difficulty locating controls, inaccurate timing, useful decomposition and confusing estimates; these are candidate codes, not observed themes. Count respondents mentioning a theme rather than counting repeated phrases from one person as separate users. If both authors code responses, describe how disagreements were reconciled rather than assuming agreement.

A negative result should explain the failure pattern and its implications. If estimates are consistently too short, task scope or category defaults may need revision. If users appreciate decomposition but distrust durations, discuss those outcomes separately. If participation is low, report feasibility and barriers without claiming the planned sample was achieved. No inferential significance or productivity improvement is assumed in advance.
""")
