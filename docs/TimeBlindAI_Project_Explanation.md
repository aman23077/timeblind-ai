# TimeBlindAI project explanation

AI integration, scheduling behavior, datasets, evaluation and next steps

Prepared for the project discussion with the professor on 12 October 2026.

## 1 Project status and the explanation to give the professor

TimeBlindAI is a productivity application for estimating task duration, breaking work into steps, planning a day around events, running focus sessions, and reviewing how predicted time compares with recorded time. Its frontend is built with Next.js and React. Its backend uses FastAPI, SQLAlchemy and SQLite by default. The project contains additional modules for goals, context, behavior and interventions; their presence does not mean that they use an LLM.

We have integrated a pretrained generative language model into task estimation and decomposition, and into proposing the order of tasks for a schedule. Python still creates the actual calendar blocks and enforces time constraints. The selected local provider is Groq and the selected model is `openai/gpt-oss-120b`. The local API key works. The integration is a working prototype, but our small pilot did not establish better duration accuracy. The public Render site has not been updated through this work.

A useful explanation to say aloud is: "Previously, our live application estimated time using rules and historical adjustments. We also had a separate linear regression experiment. We added a pretrained LLM to interpret the task description, produce a duration estimate and steps, and suggest task order. A deterministic scheduler validates and places the work around deadlines, dependencies and events. We tested integration successfully, but the duration pilot showed poor reliability and accuracy. Our next research step is to collect better completion data and test personalized estimates prospectively."

The distinction between working integration and accurate predictions matters. A model can return correct JSON, explain a task plausibly and still predict a duration badly. A generated schedule can be feasible without being optimal or especially useful. The report treats these as separate questions.

## 2 What existed before and what we added

| Area | Earlier implementation | Current implementation |
| --- | --- | --- |
| Duration estimates | Rule tables, title keywords, difficulty and quantity multipliers, optional starting estimate | LLM estimates when enabled; existing rules remain available for disabled AI and labeled fallback |
| Personalization | Historical actual to estimate ratios, bounded adjustments and feedback rules | Up to six completed examples belonging to the requested user are supplied to the LLM; no extra multiplier is applied to its answer |
| Task steps | Handwritten decomposition templates | Generated steps with titles, rationale and durations; validated before use |
| Schedule order | Deterministic sorting | LLM proposes an order; Python can skip infeasible candidates while placing the feasible tasks |
| Calendar placement | Python scheduler | Python scheduler with deadline, dependency, timezone and event reservation checks |
| ML research | CSV export, baseline analysis, linear regression training script and saved JSON model | Preserved as research artifacts; not loaded by the inspected live estimation route |
| Model failures | No external LLM request required | Safe categories, specific fallback messages and optional strict HTTP 503 mode |
| Evaluation | Earlier baseline and regression reports | Dataset audit, chronological holdout comparison, live provider checks and isolated tests |

The previous live estimator was not the saved regression model. Inspection of the task route showed rule-based estimates and personalization code. The regression training script produced an artifact on disk, but the runtime did not load it. Saying that we replaced an already deployed regression predictor would therefore misdescribe the repository.

The rules begin with task-type defaults, such as 35 minutes for reading, 50 for study and 65 for coding. Quantity can replace the base estimate, difficulty uses multipliers of 0.85, 1.0 and 1.25, and title keywords can add complexity. If a starting estimate is supplied, the rules blend 70% of their calculated value with 30% of that estimate. Historical personalization smooths ratios toward 1 with a prior weight of six and bounds the overall multiplier between 0.9 and 1.25. These are programmed heuristics, not learned LLM weights.

## 3 Which AI is integrated

Groq is the service hosting the model. GPT-OSS 120B is the language model. The `openai/` prefix in its Groq model identifier identifies the model author; it does not mean that these requests use the OpenAI API or OpenAI credits. The backend sends requests to Groq's Chat Completions endpoint using the private Groq key. Groq documents support for strict JSON-schema outputs on this model. [S1, S2]

The model is pretrained and generates text token by token. In our application that text must be a JSON object matching an explicit schema. A schema describes required fields, their types and bounds. The backend then checks relationships that the schema alone does not establish, such as whether step durations sum to the total. Structured output controls format; it cannot establish that a proposed duration reflects this person's actual working speed.

This is API inference. We do not run the 120B model on the user's computer, train it from scratch, or fine-tune its weights on the 47-row CSV. Supplying relevant completed tasks in a request is few-shot prompting. Zero-shot prompting supplies no historical examples. Neither changes model weights, so an updated history record affects a later prompt rather than retraining the hosted model.

OpenAI Responses support remains as an optional provider. The earlier connection attempt used `gpt-4.1-mini-2025-04-14` and was rejected with `credit_balance_exhausted`. We switched to Groq because the user wanted a free option. A Groq failure never triggers an automatic paid OpenAI request. The normal alternative is a clearly labeled rules fallback.

The current provider client uses a 25-second timeout and a 4,000-token output cap by default. GPT-OSS requests use low reasoning effort and exclude separate reasoning text from the returned content. The client does not enable tools, browser search, arbitrary endpoints, code execution or automatic retries. No vector database, embedding model or retrieval-augmented generation framework was added.

Groq's published free limits for this model are 30 requests per minute, 1,000 per day, 8,000 tokens per minute and 200,000 per day. Limits apply to the organization and the account limits page is authoritative. The evaluation script spaces request starts by one minute. The app itself does not yet provide distributed quota management or per-user rate limiting. Free access is quota-limited, not an unlimited production capacity guarantee. [S3]

## 4 How information moves through the application

1. The user enters a task title, notes, task type, difficulty, quantity and optional deadline in the frontend.
2. The frontend posts those fields to `/api/v1/tasks/decompose`. The normal task form does not supply a starting duration.
3. The backend retrieves a bounded selection of relevant completed tasks for that user and constructs the model request.
4. Groq returns a structured estimate, planning range, assumptions, explanation and steps.
5. Pydantic and application validators check the response. Python computes whether the estimate fits before the deadline.
6. The frontend saves the task with the returned estimate and saves the generated steps through the existing task APIs.
7. A schedule request supplies a local planning date, start time, end time and break length. The backend loads unfinished tasks and dependencies.
8. The LLM proposes the order of all supplied task IDs. Python checks that every ID appears exactly once, then places only feasible blocks.
9. The frontend displays scheduled blocks separately from tasks that were not scheduled. Starting a task block opens a linked focus session.
10. Session completion records elapsed time and feedback. Later estimates can use the completed task history; the review pages compare estimates and actuals.

The frontend never needs the private model key. API calls originate in the backend. Titles and notes sent for estimation, and task titles and metadata sent for ordering, are disclosed to the selected external provider. Omitting emails or user IDs does not make natural-language task text anonymous.

The request scopes history to the supplied user ID, but the public API still lacks authenticated ownership enforcement. An application must authenticate a caller and check ownership before it can safely trust that ID. CORS is a browser access policy, not authentication or protection against direct HTTP requests.

## 5 How an AI duration estimate is produced

For estimation, the backend includes title, description, type, difficulty, quantity, optional starting estimate, optional deadline and current time. It omits the user ID from the model task payload. History retrieval considers at most sixty recently updated completed tasks with positive actual duration up to 1,440 minutes, prefers the same task type, then includes at most six examples. Each example contains title, type, difficulty, quantity and actual minutes. Emails, identifiers and free-text session feedback are excluded.

The prompt tells the model to treat task text as data rather than instructions, estimate the full task, state assumptions for ambiguous scope, and avoid shrinking duration merely to satisfy an impossible deadline. Relevant historical examples can influence its suggestion, but they do not establish a calibrated personal prediction. The history selection is a simple bounded query and sort, not semantic vector search.

The generated total and range endpoints must be integer minutes between 5 and 1,440. The lower endpoint must be no greater than the estimate, and the estimate no greater than the upper endpoint. There must be one to twelve steps; each step must last between 5 and 480 minutes. Step titles and rationale are bounded, assumptions are bounded, and extra fields are rejected. Step minutes must sum exactly to the total. A response failing these checks is not accepted as an AI success.

The API returns source, model name, prompt version, range, assumptions, explanation and history example count. Without three relevant examples it returns a low confidence label; with at least three it uses medium. These are heuristic labels, not measured probabilities. The approximate lower and upper duration range is a planning suggestion, not a statistical confidence interval.

In the recorded synthetic test, "Read 10 textbook pages and take brief notes" received 35 minutes, a range of 30 to 45 minutes, and steps lasting 20, 10 and 5 minutes. That demonstrates a coherent response. It is not an observed completion record and was not inserted into the user's production task history.

Python compares the full estimate with the minutes available before the deadline. If insufficient time remains, the response reports overflow rather than presenting a compressed estimate as the full completion time. Successful LLM estimates do not receive the old historical multiplier again. Existing saved task durations remain unchanged until a user changes or re-estimates them.

## 6 What a generated schedule actually is

A schedule is the collection of time blocks with concrete start and end times. The explanatory paragraph is an LLM's proposed order, not the final calendar. The new UI labels it "AI suggested order" and identifies the actual scheduled time blocks below it. The frontend shows browser-local formatted times; planning-window conversion uses the saved user IANA timezone, such as Asia/Kolkata, and stores block timestamps in UTC. Those timezones must be consistent for a clear display.

The scheduler loads pending and in-progress tasks. The LLM receives task IDs, titles, types, priority, saved estimated duration, deadline and dependency IDs, plus the planning window. It returns all task IDs once with a brief proposed-order explanation. A missing ID, duplicate or invented ID fails validation. The ordering request supports up to sixty unfinished tasks.

Python translates the requested local start and end clocks into UTC using the saved timezone. It reserves fixed events and their preparation, commute, get-ready and departure-buffer time, then merges overlapping reservations. If an event has no end time, it conservatively reserves the rest of that day's planning window. An old event with no end does not keep blocking later days. The current event form does not collect an end time; the API supports it.

Within each free gap, Python considers tasks in the proposed order and selects the first feasible task. A task needs its saved estimate, with a minimum scheduling duration of fifteen minutes, plus a protective buffer. It must finish before both the planning-window end and its deadline, and its prerequisites must already be completed or placed earlier. An infeasible first-ranked task can therefore be skipped while another task is placed.

Medium difficulty adds five buffer minutes and hard difficulty ten. Historical delay, overrun and interruption feedback can add more, with a total cap of thirty minutes. Risk labels come from this buffer calculation, not from the LLM. After at least fifty minutes of accumulated work, the scheduler adds the requested break between tasks where enough room remains. It does not insert a break inside one long task.

This is a greedy scheduler. It does not prove the best possible arrangement, backtrack through every alternative, or split a long task across several gaps. It can defer work even when a more sophisticated splitting or optimization method could produce a better plan. Schedule recovery remains deterministic. Drafts are replaced only after generation succeeds; schedules containing active or completed blocks require recovery rather than regeneration.

## 7 Why the screenshot shows tasks that were not scheduled

"Deferred" originally meant not placed in this generated plan. It does not mean deleted, completed, automatically postponed to tomorrow, or removed from the user's task list. The UI now says "Tasks not scheduled" and "Not scheduled in this plan" to make that distinction explicit.

The screenshot already contains a schedule: the task "gai" is placed from 4:00 pm to 6:35 pm. Its saved estimate is 150 minutes and its medium-difficulty protective buffer is five minutes. Thus the calendar reservation lasts 155 minutes even though the task work estimate is 150. The two other cards describe work that the scheduler did not place.

The saved "go gym" record has a deadline of 14 September 2026, at 18:15 UTC, or 11:45 pm in Asia/Kolkata. That deadline predates a 12 October plan. Under the current hard-deadline rule, this task cannot be placed after its deadline. The AI paragraph recommending the already overdue gym task as urgent does not override Python's constraints. If the task is still wanted, the user should intentionally update or remove the stale deadline and generate again. We did not change that deadline automatically.

The shown "dsa" task has a saved estimate of 300 minutes and medium difficulty. It needs 305 uninterrupted minutes with its five-minute buffer. The form's default window is 4:00 pm to 10:00 pm, or 360 minutes. If that default was used, after gai's 155-minute reservation, at most 205 minutes remain even before other event reservations or breaks. Five hours of DSA cannot fit there. The screenshots do not show the selected end time, so the 205-minute calculation is explicitly conditional on using the default.

The other two tasks would require 155 + 305 = 460 minutes even without gym, fixed events or a between-task break. They need more than a six-hour window. The practical choices are to start earlier or end later, select a different day, reduce task scope, or create smaller DSA tasks. With the current implementation, generated task steps do not automatically become separate calendar blocks.

The new backend explains overdue deadlines, blocked prerequisites, insufficient remaining minutes and fragmented free time separately. It reports required time including the protective buffer and suggests an appropriate action. It still respects the constraints; showing a fuller explanation does not make an impossible schedule feasible. The schedule ordering prompt now also tells the model not to describe an overdue task as able to meet its deadline, and is versioned separately as `timeblind-schedule-v2`.

## 8 What the timers and feedback contribute

Focus sessions connect to a task and optionally a scheduled time block. Starting a scheduled block marks it active and links a session. Completion updates the session, the block, and the task's actual duration. The inspected session route sums ended minus started time across completed sessions for that task and marks the task completed when a session is completed.

This matters for label quality. The stored actual is elapsed session time, which can include pauses or interruptions; it is not guaranteed to be uninterrupted focused work. Completing a session may also mark a larger task complete, even if the user only did part of the intended scope. That can explain noisy completion labels, but it is a data-quality risk rather than a demonstrated cause of every poor prediction.

Feedback includes longer or shorter than expected, reasons such as interruption or difficulty, and notes. The rules use some feedback signals for historical adjustments and buffer calculation. The LLM history prompt does not currently include free-text feedback notes. Personalization in this prototype is therefore narrower than every available field in the database.

We need separate task completion and session completion, an explicit completion timestamp, focused time and wall-clock time, pause duration, interruption time, and completed scope. Otherwise the system may learn or evaluate against a mixture of partial work, interrupted time and true completion time. A target task's eventual feedback and session count must not be supplied as information supposedly known before that task starts.

## 9 The dataset that is actually in the repository

The main project dataset is `data/training/timeblind_training_data.csv`, exported from tasks and session history by `scripts/export_training_data.py`. It contains one row per exported task, with aggregate session statistics and latest session feedback attached. It is a pilot convenience sample of the app's records, not a representative population study. We have not established that every row is a genuine independent human observation rather than a demo or test record; provenance must be reviewed before publication.

The file has 47 rows, 7 user IDs and 21 columns. Its task creation dates range from 20 March 2026 to 14 September 2026. The present CSV therefore does not include the newer October tasks shown in the screenshot. The live application reads its database for history; it does not load this CSV into every model request. The dataset was not overwritten or refreshed during this explanation.

There are 34 rows marked completed and 13 pending. Thirty-three rows have a positive actual duration and an estimate. The stricter evaluation audit requires completed status, actual duration between 1 and 1,440 minutes, estimated duration between 5 and 1,440, and conservative deduplication by user, normalized title and creation day. This leaves 28 usable unique completed rows.

The 19 exclusions are 14 rows with a missing estimate or actual duration, three rows with both numeric values but non-completed status, and two same-user/title/day duplicates. Exclusion categories are applied in that order and are mutually exclusive in the audit. A repeated title can be a legitimate repeat task, so deduplication should be reviewed rather than treated as universal ground truth.

Actual duration among the 28 usable records ranges from 35 to 341 minutes, with mean 98.14 minutes. Assignment tasks dominate the export, with 26 of 47 records. Study contributes eleven, reading three, generic two, meeting preparation two, and errand, coding and writing one each. There are no exercise rows in this snapshot, so the gym estimate is not validated against exercise completion examples from this CSV.

Appendix A contains every row's numeric estimate, actual, type and audit outcome, using local row labels instead of raw user IDs and titles. Appendix B explains all 21 fields. The original file remains the authoritative source for full task titles and feedback. The report's reduced table deliberately excludes free-text notes and account identifiers; it is a data review, not a new training dataset.

Dataset SHA256 at review: `b347bac4d05a6bc00869bfea31b9c0edd587e0e635f31f3b1515328a21856c3a`. This fingerprint helps identify the exact snapshot and does not prove data quality, consent or provenance.

## 10 Earlier baseline and regression experiments

The saved baseline report describes 47 exported rows and 33 rows with positive estimated and actual time. It uses 26 training and seven test rows. Its recorded test mean absolute errors are 68.00 minutes for raw estimates, 69.71 for a global actual-to-estimate ratio, and 68.14 for task-type and difficulty group ratios. This baseline uses a different selection and split from the new strict audit.

The saved linear regression report describes 31 supervised rows, 24 training rows and seven test rows, with raw estimate MAE 43.00 minutes and linear regression MAE 29.27. These are the numbers recorded in the artifact, not a fresh rerun against the current snapshot. The feature set includes estimated duration, quantity, whether a deadline exists, one-hot task type and difficulty, and `completed_session_count`.

Linear regression predicts a number from weighted features plus an intercept. Its script standardizes numeric features and fits weights using gradient descent. It does not generate task steps or natural-language explanations. The saved report's split and dataset counts differ from the new evaluation, so its MAE cannot be directly compared with the new LLM MAE.

The important methodological problem is `completed_session_count` for the task being predicted. That count is an outcome of working on the task and is unavailable at creation time. Using it in a prospective duration predictor leaks future information. Historical counts from earlier tasks could be valid inputs if constructed before prediction, but that is a different feature. The reported 29.27-minute error is therefore not evidence that a deployable creation-time regression model achieved that accuracy.

We preserved the regression files to document the earlier experiment. We did not retrain, deploy or silently use that artifact as the generative model's fallback. The fallback remains the application rules.

## 11 How we evaluated the LLM

The new evaluator first audits the CSV and sorts eligible rows by creation time. It reserves the latest 20% as a holdout: with 28 eligible rows, 22 are earlier and six are held out. The earlier rows are available for development, but no LLM weights were trained on them. Calling them a 22-row LLM training set would be incorrect.

The evaluator compares recorded estimates, current rules and optional live LLM predictions on the held-out records. It sends title, type, difficulty, quantity, deadline and creation-time context, omitting user IDs, outcome feedback, actual duration, error ratio and the target task's eventual session count. Because the CSV lacks task completion timestamps, it supplies no historical examples; otherwise a supposed prior example could actually have become available after the predicted task.

The first live experiment also supplied each task's stored starting estimate. The model reproduced that value in five of six cases. The normal task form does not supply a starting estimate, so we corrected the evaluator's default to omit it from both rules and model inputs. The first report was preserved rather than overwritten. `--estimate-input stored` reproduces the initial input convention. The production duration prompt was not tuned repeatedly against these six outcomes.

Mean absolute error is the average of absolute predicted-minus-actual differences, measured in minutes. For example, predicting 90 minutes for a task that actually took 60 contributes a 30-minute error. Median absolute error is the middle absolute error and is less sensitive to a single extreme miss. Failure rate counts unusable model calls. Range coverage counts successful predictions whose proposed lower and upper bounds contain the actual duration. Latency is the elapsed request time.

The evaluation prompt is explicitly labeled `zero-shot-v1`; the production duration prompt is `timeblind-v1` and can use completed history. Evaluation lacks descriptions because the CSV does not export them. Thus the test exposes a useful weakness but is not an exact prospective test of production personalization. Also, sorting by task creation time is weaker than knowing prediction and completion times for every historical record.

## 12 Recorded results and their interpretation

| Experiment | Valid AI responses | Raw estimate MAE | Rules MAE | LLM MAE |
| --- | --- | --- | --- | --- |
| Stored starting estimate supplied | 6 of 6 | 61.67 min | 52.67 min | 61.33 min |
| Starting estimate omitted | 3 of 6 | 61.67 min | 49.00 min | 202.00 min on three successes |

Both live evaluations were recorded on 8 October 2026 with Groq GPT-OSS 120B. The seeded test averaged 2.13 seconds per call and had no failures. Its ranges covered none of the six actuals. The corrected unseeded test averaged 2.26 seconds per call, with a 50% failure rate and zero range coverage on its three valid responses. The older error category combined invalid response and unavailable service, so the exact causes of those historical failed calls were not recorded.

The 202-minute LLM MAE uses only the three successful predictions. It is not a full six-task score and must not be presented as directly comparable without its sample-size limitation. On those same three tasks, the rules' MAE was 33 minutes. The evaluator did not replace failed LLM predictions with rules and then call those AI successes.

| Holdout row | Actual | Recorded estimate | Rules without starting estimate | LLM without starting estimate |
| --- | --- | --- | --- | --- |
| H1 | 60 | 90 | 60 | 180 |
| H2 | 60 | 86 | 60 | 120 |
| H3 | 120 | 82 | 80 | Failed |
| H4 | 42 | 78 | 47 | Failed |
| H5 | 180 | 36 | 30 | Failed |
| H6 | 174 | 78 | 75 | 600 |

These results do not support an accuracy improvement claim. They suggest that ambiguous scope, limited personal context and response reliability need attention. Those are plausible research directions, not proven explanations for each miss. Six tasks and seven users are insufficient for a general claim that all LLMs are poor predictors or that this model is reliable for this application.

Integration checks answer a different question. The recorded 8 October live checks returned HTTP 200 for an estimate and a schedule, with AI source labels. On 12 October, an isolated synthetic nine-task schedule also returned AI output, placed all nine tasks, respected a dependency and avoided a fixed event. These checks used an in-memory database. They establish that requests, parsing and scheduling constraints can work, not that human completion durations are accurately predicted.

The current automated suite passes 64 tests. It covers structured provider contracts, invalid answers, missing credentials, failure categories, no paid-provider fallback, user-scoped bounded history, timezone conversion, dependency cycles, event conflicts, draft preservation, and the new deferral explanations. Mocked provider tests establish software behavior; they do not establish live model quality.

## 13 Public datasets researched and their actual role

Our own completion records are the primary candidate data for personal duration evaluation. Public activity or planning datasets measure different outcomes, so they should not be mixed into our duration labels just because they contain times or tasks.

The US Bureau of Labor Statistics American Time Use Survey provides time diaries and activity coding. It can help examine broad activity duration distributions and inform background discussion. A diary episode such as studying for an hour is not a measured completion time for a specified DSA assignment. Its population and context also differ from this app's users. The data files and documentation are available from BLS; no ATUS file was downloaded or added to model training in this project. [S4]

Google DeepMind's Natural Plan benchmark includes trip planning, meeting planning and calendar scheduling tasks, with inference datasets and evaluation code. It is a useful external source for testing whether a planning system respects supplied constraints. It does not provide this user's measured completion time for reading or coding. Its repository identifies Apache 2.0 for software and CC BY 4.0 for other materials; inspect the exact files and attribution terms before redistribution. It has been researched but not imported into this repository. [S5]

Microsoft TaskBench focuses on task decomposition and dependency or tool planning. It is a possible reference for evaluating generated plans. It is not a dataset of measured human task completion durations. We have not imported it, fine-tuned on it, or claimed a TaskBench score. Its repository, data definitions and current license must be reviewed before choosing a specific subset. [S6]

Pretraining data used upstream to build GPT-OSS is separate from all three of these candidates and from our local CSV. We have not assembled or audited the original model pretraining corpus. General benchmark or model-provider capability claims do not establish duration accuracy on TimeBlindAI.

## 14 Code changes and storage

| Component | Main responsibility |
| --- | --- |
| `app/core/config.py` | Provider, model, private key, enabled flag, timeout, token cap and failure mode |
| `app/modules/reasoning/llm.py` | Fixed provider endpoint, structured JSON request, response parsing and safe failure categories |
| `app/modules/reasoning/generative.py` | History selection, prompts, estimate/order schemas, semantic validation and labeled fallback |
| `app/modules/tasks/routes.py` | Existing decomposition route delegates to generative estimation |
| `app/modules/tasks/schemas.py` | Description input and optional AI metadata in responses |
| `app/modules/schedules/planner.py` | Feasible calendar placement, reservations, dependencies, buffers and deferral reasons |
| `app/modules/schedules/routes.py` | User timezone conversion, draft protection and atomic generation persistence |
| `frontend/lib/api.ts` | Types for AI metadata and existing API calls |
| `frontend/components/timeblind-shell.tsx` | Notes forwarded, AI source/range/assumptions displayed, clearer final schedule and unscheduled sections |
| `scripts/evaluate_generative.py` | Offline audit and optional live holdout comparison |
| `scripts/smoke_generative.py` | Isolated live estimate and schedule connection checks |
| `tests` | Isolated database and mocked-provider regression checks |

Tasks persist the saved estimated minutes and generated steps. Schedules persist the source through `generated_by`, using `llm_validated` when AI ordering was accepted. The immediate response includes model and prompt metadata, narrative and unscheduled reasons. Full prediction provenance, ranges, assumptions and prompt details are not yet stored as dedicated prediction records. Reloading a saved schedule therefore does not reconstruct every detail of the original generation response.

The project added the HTTP client dependency and timezone data support. It does not need a Groq SDK because it sends HTTP requests directly. The `.env` file is ignored by Git and contains local private settings. No key is included in this report, example source configuration or frontend environment.

## 15 Configuration local use and the professor demonstration

The local selected settings are `LLM_ENABLED=true`, `LLM_PROVIDER=groq`, `LLM_MODEL=openai/gpt-oss-120b`, and `LLM_FAILURE_MODE=fallback`. A private `GROQ_API_KEY` must be present on the backend. The settings cache requires a backend restart after changing `.env`. The inspected development server uses code reload, so Python code changes reload automatically. AI can be disabled with `LLM_ENABLED=false`.

The backend command from the repository root is `.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000`. The frontend runs with `npm run dev` inside `frontend`. Its API base defaults to `http://127.0.0.1:8000`; an explicit frontend environment value can point it elsewhere. `/health` confirms that the backend is responding, not that model credentials or free quota are usable.

For a demonstration, create a new small task with clear scope, such as reading ten pages and writing two bullet notes per page. Show the AI source, range, assumptions and steps. Use a future deadline and a generous planning window. Add an event with known reserved time, then generate a schedule and inspect actual block times. Show one intentionally oversized task and explain its deferral. Start a scheduled task session, complete work and feedback, and show the review view. Keep synthetic demo records distinguishable from research observations.

Existing task estimates are not recalculated every time a schedule is generated. If the user added a five-hour task earlier, ordering uses that saved five-hour value. To study better duration prediction, evaluate a new estimate or deliberately revise scope rather than expecting schedule generation to shorten the task.

The public Render services remain separate from local development. Deployment requires publishing updated backend and frontend code, private backend model settings, the real database configuration, appropriate CORS origins, and the frontend's actual backend base URL. Public activation should follow authenticated ownership checks and per-user request limits so the shared quota and task history are protected.

## 16 What we will do next

First, improve schedule usability. The immediate changes explain unscheduled tasks and distinguish proposed order from calendar blocks. The next implementation should add an event end-time field, allow intentional revision of stale deadlines, and offer splitting a long task into several focus blocks. A soft-deadline option could allow overdue work with an explicit late warning; it must be a user-selected policy rather than silently ignoring deadlines.

Second, fix label collection. Separate completing a session from completing the whole task, record completed scope and task completion timestamps, and distinguish focused minutes from paused or interrupted elapsed time. Persist each prediction before work begins, with source, provider, model, prompt version, range, relevant-history cutoff and estimate. Later feedback must link to that exact prediction instead of a mutable task value alone.

Third, validate personalization and model choice prospectively. Compare rules, zero-shot LLM and LLM with only prior personal history on the same new tasks. Investigate cheaper strict-schema candidates such as GPT-OSS 20B or another supported model only after verifying current model support and account quotas. A candidate is not an improvement until it passes the planned evaluation. More general benchmarks or larger model size do not establish better human duration estimates.

Fourth, implement public access controls and quota management. Authenticate users, check ownership on reads and writes, add per-user request budgets, bound concurrency and surface quota-reset behavior. Review provider privacy terms and the user-facing disclosure for external task content. Then deploy and verify both the production API connection and the frontend source labels.

Fifth, consider richer scheduling. A constraint solver or stronger scheduling algorithm could search alternative orders, handle preferences, place partial focus blocks and explain tradeoffs. This is a separate experiment from replacing the duration predictor. Scheduling with supplied durations and predicting those durations need distinct datasets and acceptance criteria.

Fine-tuning is a later conditional option. It would require a supported model or local training setup, sufficiently reliable examples, a stable target definition and evidence of a recurring error that prompting cannot solve. The current 28 eligible records do not support a responsible broad fine-tuning claim. We do not need to train a new foundation model to continue this prototype.

## 17 Proposed research experiment

Start with a clearly labeled pilot collection target, for example five to ten consenting users and fifty to one hundred completed tasks per user over several weeks. This is a practical starting target, not a statistical power calculation or a guarantee of representativeness. Review recruitment, consent and study requirements with the professor before research collection.

Record task scope, quantity units, familiarity, intended outcome, deadline policy and task type before prediction. Save all method predictions at the same prediction timestamp. Record actual focused duration, wall-clock duration, interruptions, final completed scope and completion timestamp after work. Retain partial and failed tasks with clear labels instead of silently treating them as completed observations.

Freeze the evaluation procedure before comparing models. Use chronological splits with history strictly preceding each prediction, group genuine duplicates, and evaluate both known users and unseen users. Preserve a final untouched prospective test period after development. The six existing holdout results are now diagnostic pilot evidence and should not be repeatedly tuned into a claimed independent benchmark.

Report MAE and median absolute error, signed error, underestimation and overestimation rates, usable-response rate, latency, quota consumption and planning-range coverage. Stratify by user, type, scope and familiarity only where counts support it. For schedules, separately record deadline/event/dependency violations, completion rate, fraction deferred and user-rated usefulness. Small subgroups should retain their sample sizes instead of yielding broad percentage claims.

Agree on acceptance criteria before evaluation. For example, a replacement predictor should improve error over the rules on the same eligible cases while maintaining a predefined usable-response rate. These thresholds need to be chosen with the professor, not invented after viewing results. An LLM-assisted decomposition feature could still be useful even when the duration predictor fails that acceptance test.

## 18 Questions the professor may ask

**Did you train your own LLM?** No. We call a pretrained hosted model. Our contribution is application integration, prompting with bounded personal history, validation, constraint-aware placement and evaluation.

**What happened to regression?** The repository contains an earlier offline regression experiment, but the inspected live estimator used rules. The regression artifact is preserved and not loaded by the new runtime. Its target-task session-count feature creates prospective leakage.

**What dataset trained the current AI?** No local dataset was used to train its weights. The CSV supports our audit and evaluation; completed database records can be examples in an inference request. Upstream model pretraining is a separate process.

**Is the model better than the previous method?** The present evidence does not show that. The corrected six-task pilot had three valid predictions with large errors. We can demonstrate functionality and constraints, but must report accuracy honestly.

**Why does an AI schedule defer tasks?** AI proposes an order. Python enforces actual deadlines and available calendar slots. Deferred tasks remain unfinished in the task list, with an explanation of the constraint preventing placement.

**Is it a fully generative planner?** Language interpretation, estimates, steps and order use a generative model. Final time arithmetic and validation use deterministic Python. This hybrid design avoids trusting generated timestamps as the calendar's sole authority.

**Does it diagnose or treat ADHD or time blindness?** No clinical diagnosis, treatment efficacy or medical outcome has been established. The project is a productivity assistant; supportive language and timer features do not establish clinical benefit.

**What is new in this project?** The concrete implementation combines task-text interpretation and personal completed examples with validated calendar placement and a feedback workflow. Novelty as a research contribution must be assessed against related work; the integration alone is not evidence of a new model architecture or a state-of-the-art result.

**What will make the next result credible?** Better labels, persisted predictions, history restricted to what was known at prediction time, frozen comparisons against the same baselines, and an untouched prospective test set with failure cases included.

## 19 Terms and source material

Inference means calling an existing model to produce a result. Fine-tuning means updating model weights with training examples. A prompt is the instructions and context in a request. A token is a unit of text processed by the model. Few-shot prompting adds examples to that request. A holdout is data reserved for evaluation. Leakage is using information that would not be available at prediction time. A hard deadline prevents placing a task after that deadline. A protective buffer reserves extra time for likely variation. A deferred task is unfinished work not placed in this plan.

The local evidence comes from the current source files, `data/training/timeblind_training_data.csv`, `model_baseline_report.md`, `linear_model_report.md`, and saved JSON reports in `data/evaluation`. Dataset values in this report were checked locally on 12 October 2026. Historical evaluation values are taken from their saved reports and have not been regenerated or presented as new experiments.

[S1] [Groq structured output documentation](https://console.groq.com/docs/structured-outputs). Supports the chosen strict JSON response format; it does not certify TimeBlindAI accuracy.

[S2] [Groq GPT OSS 120B model documentation](https://console.groq.com/docs/model/openai/gpt-oss-120b). Identifies the hosted model and its capabilities.

[S3] [Groq rate limit documentation](https://console.groq.com/docs/rate-limits). Account limits are authoritative and can change.

[S4] [BLS American Time Use Survey data and documentation](https://www.bls.gov/tus/data.htm). Candidate background activity data; not imported.

[S5] [Google DeepMind Natural Plan repository](https://github.com/google-deepmind/natural-plan). Candidate planning benchmark; not imported.

[S6] [Microsoft TaskBench documentation](https://github.com/microsoft/JARVIS/blob/main/taskbench/README.md). Candidate task planning reference; not imported.

## Appendix A All dataset rows

Rows follow the original CSV order. R01 is the first data row after the header. User labels are pseudonyms local to this report. Times are minutes. n.a. means missing, not zero. Audit labels: Use = eligible; Missing = missing estimate or actual; Pending = not completed; Repeat = conservative same-user/title/day exclusion.

| Row | User | Type | Estimate | Actual | Status | Audit |
| --- | --- | --- | --- | --- | --- | --- |
| R01 | U1 | generic | 37 | n.a. | pending | Missing |
| R02 | U1 | assignment | 78 | 174 | completed | Use |
| R03 | U1 | errand | 36 | 180 | completed | Use |
| R04 | U1 | assignment | 78 | 42 | completed | Use |
| R05 | U1 | reading | 82 | 130 | completed | Repeat |
| R06 | U1 | reading | 82 | 120 | completed | Use |
| R07 | U2 | assignment | 87 | n.a. | pending | Missing |
| R08 | U2 | assignment | 86 | 60 | completed | Use |
| R09 | U3 | coding | 80 | n.a. | pending | Missing |
| R10 | U3 | assignment | 88 | 64 | completed | Repeat |
| R11 | U3 | assignment | 90 | 60 | completed | Use |
| R12 | U3 | assignment | 76 | 60 | completed | Use |
| R13 | U3 | study | 195 | n.a. | pending | Missing |
| R14 | U3 | assignment | 90 | 120 | completed | Use |
| R15 | U2 | study | 217 | 60 | completed | Use |
| R16 | U2 | writing | 73 | 60 | completed | Use |
| R17 | U3 | assignment | 76 | 60 | completed | Use |
| R18 | U2 | assignment | 78 | 60 | completed | Use |
| R19 | U3 | assignment | 96 | 60 | completed | Use |
| R20 | U3 | assignment | 97 | n.a. | pending | Missing |
| R21 | U3 | study | 76 | 96 | completed | Use |
| R22 | U3 | assignment | 97 | 90 | completed | Use |
| R23 | U3 | study | 76 | 60 | completed | Use |
| R24 | U3 | reading | 36 | 58 | completed | Use |
| R25 | U3 | study | 17 | 35 | completed | Use |
| R26 | U3 | study | 347 | n.a. | pending | Missing |
| R27 | U3 | assignment | 133 | 180 | completed | Use |
| R28 | U3 | assignment | 90 | 120 | pending | Pending |
| R29 | U3 | study | 88 | n.a. | pending | Missing |
| R30 | U3 | study | 58 | 105 | completed | Use |
| R31 | U3 | study | 81 | 120 | pending | Pending |
| R32 | U3 | study | 62 | 159 | completed | Use |
| R33 | U3 | study | 88 | 118 | completed | Use |
| R34 | U3 | meeting_prep | 39 | 60 | completed | Use |
| R35 | U3 | assignment | 115 | n.a. | completed | Missing |
| R36 | U3 | assignment | 136 | n.a. | completed | Missing |
| R37 | U3 | assignment | 136 | 341 | completed | Use |
| R38 | U3 | assignment | 136 | 100 | completed | Use |
| R39 | U3 | assignment | 168 | n.a. | completed | Missing |
| R40 | U3 | assignment | 160 | 120 | completed | Use |
| R41 | U3 | assignment | 160 | 60 | completed | Use |
| R42 | U3 | assignment | 160 | 50 | completed | Use |
| R43 | U3 | assignment | n.a. | 45 | completed | Missing |
| R44 | U4 | generic | 5 | 1440 | pending | Pending |
| R45 | U5 | assignment | n.a. | n.a. | pending | Missing |
| R46 | U6 | meeting_prep | n.a. | n.a. | pending | Missing |
| R47 | U7 | assignment | 120 | n.a. | pending | Missing |

The chronological holdout maps to the appendix as H1 = R11, H2 = R08, H3 = R06, H4 = R04, H5 = R03, H6 = R02.

## Appendix B Dataset field dictionary

The role describes whether a value is available before a new task starts. Historical outcomes may be useful only when they belong to earlier tasks and precede the prediction.

| Field | Role | Meaning and use |
| --- | --- | --- |
| `task_id` | Identifier | Links a task to sessions and steps; omitted from LLM estimation input. |
| `user_id` | Identifier | Scopes personal history; caller ownership still needs authentication. |
| `title` | Input | Task wording; sent to the model and used in conservative duplicate grouping. |
| `task_type` | Input | Category such as reading or assignment; supports rules and history selection. |
| `difficulty` | Input | User-selected easy, medium or hard; affects rules and protective buffers. |
| `priority` | Input | Task urgency preference; supplied to ordering, not the exported duration evaluator. |
| `quantity_value` | Input | Numeric scope; units are not separately exported, which creates ambiguity. |
| `status` | Outcome or state | Completed status is required by the strict duration audit. |
| `deadline_at` | Input | Optional deadline; scheduler treats it as a hard finish constraint. |
| `created_at` | Timestamp | Creation time used for audit ordering; not a task completion timestamp. |
| `estimated_minutes` | Prediction | Saved starting estimate or prior prediction; method provenance is not recorded here. |
| `actual_minutes` | Target | Recorded task elapsed minutes; audit requires positive values and completed status. |
| `estimate_error_minutes` | Derived outcome | Actual minus estimate; positive means an underestimate. Never a prospective input. |
| `actual_to_estimate_ratio` | Derived outcome | Actual divided by estimate; an outcome-based evaluation value. |
| `completed_session_count` | Outcome | Count for the target task is unknown at creation and leaks future information. |
| `total_elapsed_minutes` | Outcome | Sum of recorded completed session elapsed minutes; requires careful time semantics. |
| `avg_delay_minutes` | Outcome | Average delay for completed sessions; prior tasks can inform protective buffers. |
| `avg_overrun_minutes` | Outcome | Average overrun; valid historical context only if known before prediction. |
| `latest_difficulty_feedback` | Feedback | Last completed-session assessment; collected after work, not before it. |
| `latest_feedback_reasons` | Feedback | Comma-separated reasons such as interruption; omitted from LLM history. |
| `latest_feedback_notes` | Free text | Potentially identifying notes; excluded from LLM requests and this row appendix. |
