# November 2026 participant pilot

This is the launch and analysis protocol for the BTP report due November 25, 2026. The target is approximately 20 adult participants completing three real tasks each. Sixty completed records is a recruitment target, not an observed result or a statistical power calculation.

## Dates and responsibilities

All study dates below use Asia/Kolkata time.

| Date | Action | Deliverable |
| --- | --- | --- |
| November 21 | Review the scope with the supervisor, deploy, verify persistence and run two practice accounts | Frozen protocol and working participant link |
| November 22–23 | Invite approximately 20 friends; each attempts three naturally occurring tasks | Consent, prospective estimates, timings and feedback |
| November 23 at 23:59 | Stop recruitment and record the analysis cutoff | Private export and count of incomplete records |
| November 24 | Validate records, calculate statistics, generate figures, write findings and limitations | Completed results chapter and revised abstract |
| November 25 | Check references, author contributions, layout and declarations; submit | Final report PDF |

Practice accounts must not contribute to reported results. Use separate accounts and withdraw those accounts before the research export. Do not silently include synthetic accounts, ordinary legacy users or developer demonstrations. Keep a private recruitment log containing number invited, number joined, withdrawals and technical failures. Do not put names or emails in the report.

## Questions the pilot can answer

1. Can participants complete the consent, task planning, timing and feedback flow?
2. On the same completed tasks, how do participants' initial guesses compare with frozen unpersonalized rules estimates?
3. How do participants rate ease of use, plan clarity, usefulness, estimate trust and willingness to use the app again?

This is an exploratory convenience-sample study. It cannot establish that TimeBlindAI improves productivity, treats timeblindness, detects cognitive states, or outperforms other products. Twenty participants making three records each are twenty participant clusters, not sixty independent participants. Showing the app estimate may itself influence work pace; this is an in-use comparison, not a blinded predictor trial.

## Participant experience

Use the existing application with a dedicated `/study` entry page. A separate Google Form is unnecessary for the core study because the built-in form links responses and prospective predictions to the same account. Keep a private incident log for problems reported outside the app.

1. Read the study information and create or sign in to an account.
2. Confirm age 18 or above and explicit study consent. Answer the baseline planning-frequency question.
3. Pick a real task that has not started and has a concrete completion condition. Prefer 15–60 minutes; smaller scope is better than an open-ended “study all day”.
4. Enter the title, category, difficulty and personal duration guess. The backend saves the guess and a rules prediction before revealing the app prediction. The user guess is not fed into the rules.
5. Open the main app in another tab to inspect the saved task decomposition and try the scheduler. Use the `/study` timer for pilot tasks; do not start a second main-app focus session for the same task.
6. Start the study timer when work begins. Record breaks and unrelated work separately. Closing the browser does not pause server timing.
7. Finish the record, report break minutes, indicate completion and scope changes, and choose a friction reason. If the timer was forgotten or unreliable, select unfinished. Predictions and finished outcomes are not editable through the study API.
8. Repeat for three real tasks over two days. Do not create fake completions to meet the target.
9. Submit five ratings and optional written feedback. Early dropouts may submit feedback after one attempted task. Stop or withdraw at any time.

The study creates ordinary tasks and steps so they appear in the app. It also saves independent study snapshots; later editing a task in the main app cannot rewrite the original prediction comparison.

## Form specification

### Study information and consent

The page identifies the project team and contact, describes voluntary participation and expected time, distinguishes account email from pseudonymous report records, lists collected data, gives withdrawal/deletion instructions and sets a proposed deletion date of December 25, 2026. Confirm this retention commitment with the project owner before invitations. No diagnoses or medical history are requested.

Required checkboxes: “I am at least 18 years old” and “I have read the information above and agree to take part in this study.” Account registration's consent preference is not sufficient by itself for pilot enrollment.

Baseline item: “How often do tasks take longer than you initially expect?” Options: never, rarely, sometimes, often, very often. This is a descriptive custom question, not a validated timeblindness scale.

### After each attempted task

Capture completed versus unfinished or unreliable timer, break minutes, whether scope changed, and one friction reason: none, interruption, harder than expected, unclear scope, technical problem, other. Keep raw elapsed time and reported break time so the work-time calculation can be audited.

### Final questionnaire

Use five separate custom questions on a five-point agreement scale: 1 strongly disagree, 2 disagree, 3 neutral, 4 agree, 5 strongly agree.

- The app was easy to use.
- The task plan was clear.
- The app helped me plan my work.
- I could rely on the time estimates.
- I would use this app again.

Optional questions: What helped you most? What was the biggest problem? What should we improve first? These five ratings are not SUS and must not be converted into or reported as a standardized usability score.

## Freeze the experiment

The dedicated study task endpoint always calls the deterministic task decomposer with multiplier 1.0, no user estimate input and no LLM request. Its method label is `rules-unpersonalized-v1`; protocol label is `nov2026-pilot-v1`. Record the deployed Git commit, deployment time and exact configuration in private study notes. Keep this version fixed during collection. Existing main-app AI functionality remains a separate implementation feature; set `LLM_ENABLED=false` for a consistent pilot experience unless a separately documented study is planned.

The pilot evaluates the simple rules baseline against human guesses. It does not evaluate personalized learning, an LLM, or reminder effectiveness. Historical AI evaluation and synthetic scheduler checks belong in separate report subsections. Three tasks per person cannot support claims about long-term personalization.

## Timing and eligibility

Study work minutes equal server elapsed minutes minus self-reported breaks and unrelated work. This is a recorded work-time proxy, not proof of uninterrupted attention. Clock time comes from the server; reported breaks may be inaccurate. Retain decimals in exports; presentation tables may round to two decimals.

Include a row in paired duration accuracy only if participation is currently consented and not withdrawn, the outcome is completed, scope did not change, and recorded work time is at least one minute. Unfinished, active, planned and scope-changed tasks remain in the participation accounting, with exclusions reported separately. Scope-changed completed tasks count as completions but not duration-valid records.

At analysis cutoff, download a snapshot and record its timestamp. Do not silently replace the dataset later. Exclude developer/practice accounts through withdrawal. Investigate impossible durations and forgotten timers using a private audit log; preserve raw values and publish the number excluded and reasons. Do not remove difficult or inaccurate tasks to improve results.

## Statistics and report figures

| Result | Calculation and reporting |
| --- | --- |
| Participation | Invited, enrolled, withdrawals, consenting cohort, number with three completed tasks, feedback responses; denominators stated |
| Completion | Completed tasks / started tasks at cutoff; also list planned, active and explicitly unfinished counts |
| Primary estimation error | Mean absolute error in minutes for human and rules on identical eligible rows |
| Robust descriptive error | Median absolute error and proportion with absolute error at most 15 minutes |
| Participant weighting | Compute each participant's mean absolute error, then average those participant means; report participant N |
| Feedback | N, median and counts at each score from 1 to 5 for each item separately |
| Friction | Count each friction reason among attempted finished records, including unfinished; state denominator |
| Qualitative themes | Review all responses, define a short codebook, count respondents per theme, use redacted examples only |

Recommended figures after data collection: paired participant mean-error dots for human versus rules; task actual-versus-predicted scatter; five stacked rating bars; participant flow counts. Show sample sizes and units. Use categories only when group counts are sufficient to interpret. A single average satisfaction number hides useful variation.

Report descriptive findings and individual variation. Do not run a task-level significance test treating three tasks per person as independent. A paired exploratory analysis must use participants as units, or a method that explicitly handles clustering; do not promise statistical significance with this sample. Do not train on this pilot and then claim its training accuracy as evaluation performance.

## Operator pages and data handling

`/study/admin` requires the existing explicit administrator grant. It shows aggregate counts, human/rules errors, rating distributions and a private comments viewer. `/api/v1/study/admin/export` returns participants.csv, tasks.csv, feedback.csv, summary.json and a readme. It omits account IDs, email addresses, task titles and written comments. Random participant codes remain pseudonymous, not fully anonymous; timestamps can still reveal patterns.

Study withdrawal excludes all of that participant's records from the dedicated study summary, comments and exports. Raw database records remain until operator deletion. The general administrator export is a broader operational backup, not the research cohort filter; never use it as the report dataset without separate consent filtering and review. Keep database backups and exports private, outside Git. Re-export if a participant withdraws before submission and remove the withdrawn person's rows from earlier working copies.

## Deploy and verify on the existing Render services

Use the existing Render deployment; a static Sites page alone cannot run this FastAPI application or provide its persistent database. No new service or paid plan is implied by these changes. Follow `docs/render-pilot.md` for the current backend/frontend settings. In particular, ensure `DATABASE_URL` points to persistent storage and `TIMEBLIND_BACKEND_URL` is present at frontend build time, when rewrites are generated.

Deploy the same reviewed commit to both services. Backend startup registers and creates the new study tables using the existing SQLAlchemy initialization. Existing tables are preserved. Back up the persistent database before deployment. No Render credentials or deploy hook should be placed in the repository.

Before sharing the participant URL:

- Verify `/study` and `/study/admin` load on the hosted frontend. The expected participant URL after deployment is `https://timeblind-frontend.onrender.com/study`.
- Signed-out `/api/v1/study/me` and study admin endpoints must return 401; a signed-in non-admin must receive 403 from study admin endpoints.
- With two practice accounts, enroll, save estimates, start, finish, submit feedback, inspect admin results, and download the ZIP. Confirm the guess was saved before the app estimate was shown and another account cannot access the record.
- Check one mobile device and one desktop browser. Leave a timer page and return; verify it still reflects elapsed time. Check break validation and unfinished reporting.
- Redeploy normally and confirm the same test records remain. This verifies persistence, not merely a successful build.
- Withdraw both practice accounts; confirm study counts and exports exclude them. Freeze the deployed commit and begin recruitment only after this passes.

## Invitation text to send yourself after launch verification

Hi! We are testing TimeBlindAI for our BTP. Could you try it on three real tasks over the next two days? You will enter your own time guess, try the app's plan, time your work and answer a short feedback form. There are no right answers, and negative feedback is useful. Participation is voluntary; the study page explains what is recorded and how to withdraw. Please use tasks without sensitive information. Open https://timeblind-frontend.onrender.com/study after I confirm the study is live. Thanks!

Do not send invitations before hosted verification. This text is a draft for the project owner; no messages have been sent automatically.

## Report structure and completion rules

Retain last semester's academic front matter: cover, declaration, certificate, abstract, acknowledgments, author work distribution and contents. Keep the two authors, roll numbers, advisor and institution only after the authors confirm they are unchanged. Signatures and advisor certification must be completed by the actual signatories.

Use chapters for introduction and prior-semester context, related work, objectives, architecture and ontology mapping, implementation, evaluation methodology, results, discussion and limitations, future work, and conclusion. Add consent/questionnaire and metric definitions as appendices. Replace last semester's repeated architecture promises with implementation evidence and experimental results. Eliminate the duplicate introduction and unresolved citation.

Keep the prior report's estimate-relative deviation separate from the live reminder policy's minutes-overdue/planned-duration measure; they have different numerators. Neither is a clinical timeblindness measure. Avoid describing app switches or inactivity as ground-truth distraction or cognitive load.

The report draft can be written now. Participant sample sizes, outcomes, plots, deployment date and conclusions based on this pilot remain pending until the data exists. Report a small or negative finding honestly. After the November 23 cutoff, replace pending-result tables, update the abstract and conclusion, add current screenshots and real author contributions, audit every reference, then export the final PDF.
