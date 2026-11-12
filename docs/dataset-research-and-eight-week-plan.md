# Dataset research and an eight week plan for TimeBlindAI

Sources checked on 12 October 2026. The work below is proposed; datasets have not been imported and the proposed experiments have not been run.

## Recommended research question

Can a generative model with relevant personal history estimate student task duration more accurately than rules or a generic LLM, and can a constraint-aware planner turn those estimates into useful schedules that adapt to interruptions?

Evaluate duration prediction and scheduling separately. Working API integration is established; better prediction accuracy is not established by the current pilot.

## Online datasets and their role

| Resource | What it provides | Proposed use | Important boundary |
| --- | --- | --- | --- |
| [Google DeepMind Natural Plan](https://github.com/google-deepmind/natural-plan) | Trip, meeting and calendar planning problems with reference plans and evaluation code | Begin with a fixed sample of calendar scheduling cases to test availability and conflict reasoning | Durations are supplied constraints, not measured human completion labels; adapters are needed for our API |
| [TCP dataset](https://huggingface.co/datasets/Beanbagdzf/TCP) and [paper](https://aclanthology.org/2025.emnlp-main.1142/) | Natural-language dialogue problems with interdependent temporal constraints | Test extracting constraints and satisfying ordering and time requirements | Some constraints exceed our current single-user planner; report supported subsets and do not claim a full benchmark score |
| [Microsoft TaskBench](https://github.com/microsoft/JARVIS/blob/main/taskbench/README.md) | Tool-oriented task decomposition and dependency graphs | Reference evaluation for decomposition, ordering and dependency validity | Generated tool plans are not measured human study, exercise or coding durations; adaptation is required |
| [METR public analysis data](https://github.com/METR/eval-analysis-public) and [methodology](https://metr.org/time-horizons/) | Human expert duration estimates and task/run metadata for software, ML and cybersecurity tasks | Optional external study of technical task-time estimation | Some labels are expert estimates rather than timed attempts. First verify matched public task instructions, provenance and reuse rights. Expert times do not personalize student task estimates |
| [SCHEDBench](https://huggingface.co/datasets/SCHEDBench/SCHEDBench) | 1,132 scheduling instances across six operations-research families | Optional later stress testing of feasibility and scheduling quality | Job-shop, project and rostering problems need resources and constraints the current app does not represent. Its card lists CC BY 4.0 for the release; original source suites retain their own terms |

Natural Plan is the first implementation target. TCP is a later extension. TaskBench is a reference for dependency-aware decomposition, not the core duration dataset. METR is conditional on a suitable publicly accessible task-and-label subset. Avoid claiming that time-to-close an issue, story points or a synthetic LLM-generated duration is measured focused human work.

These datasets can test and guide changes to prompts, input extraction, retrieval and planning. Downloading them does not change the hosted model's weights. Fine-tuning is a separate step requiring a supported training service or suitable local hardware, licensed training examples and a stable target definition. Published test benchmarks should not be consumed as training examples and then reported as untouched tests.

## Four substantial contributions

### Reliable task scope and personal duration estimation

Collect units, amount of work, familiarity and intended completion outcome. For an ambiguous task such as "DSA", ask how many questions, their difficulty and whether the user has practiced the topic. Select prior completed examples by scope, type, difficulty and familiarity, with every example completed before the prediction timestamp. Compare rules, a zero-shot LLM and the same LLM with personal history.

If clarification supplies extra information, give those answers to all compared methods or run a separately labeled information-gain experiment. Otherwise an apparent model improvement could simply come from receiving more useful inputs.

### Partial progress and an adaptive planner

Split a long task into bounded focus blocks, preserve its total remaining work, insert breaks, and track the parent task independently of an individual session. Replan when a block overruns or an interruption consumes available time. Keep finished and active work intact. Make deadlines explicitly hard or soft according to a user choice, with lateness disclosed rather than silently ignored.

Investigate an [OR-Tools scheduling solver](https://developers.google.com/optimization/scheduling) for searching alternative arrangements. This is scheduling optimization, not regression. Define an objective, such as prioritizing important work while reducing deferrals and fragmentation, and report solver status rather than claiming optimality whenever a timeout yields only a feasible plan. Retain an independent constraint checker.

### A prospective completion dataset

Recruit five to ten consenting volunteers and aim initially for twenty to forty completed tasks each, with practical targets adjusted to participation. This is roughly 100 to 400 records, not a statistical power calculation. Start collection early in parallel with engineering.

Persist task scope and prediction context before work. Save model/provider/prompt versions, estimate, range and history cutoff. After work, record focused time, paused time, wall-clock time, completed scope, interruptions and explicit task completion time. Finishing one session must not automatically label the whole task complete. Separate real study records from demonstrations and synthetic cases.

### A reproducible evaluation framework

Build adapters for public benchmarks and a separate app-specific suite of synthetic scenarios with known constraints and solver-checked reference plans. Include expired deadlines, dependency cycles, fragmented time, timezones, oversize tasks, missing event end times and interruptions. Synthetic durations are inputs to a planning test, not human duration ground truth.

For estimation, report MAE, median absolute error, signed error, response failure rate, latency and planning-range coverage, always with sample sizes. Compare identical tasks and information. Report all attempted calls; do not hide failures or replace them with rules and count them as AI successes.

For scheduling, report hard-constraint violations, scheduled work, deferred work, lateness for explicit soft deadlines and objective quality. Distinguish parsing failure, infeasible input, feasible solution and proven optimal solution. Follow the original benchmark evaluator when claiming its score; report any additional constraint-based scoring separately.

Freeze development and final test sets. Public benchmarks may overlap a model's upstream training data, so include newly collected prospective tasks and fresh app-specific scenarios. Report this limitation rather than claiming that all public benchmark cases are unseen.

## Proposed eight week delivery schedule

| Period | Engineering and research work | Reviewable result |
| --- | --- | --- |
| Week 1 | Fix timer/completion semantics, record scope and immutable predictions, recruit volunteers and freeze the study protocol | Data schema, collection workflow, consent process and baseline definition |
| Week 2 | Add a Natural Plan calendar adapter, independent checks and a reproducible initial benchmark | Versioned benchmark sample, baseline results and failure taxonomy |
| Weeks 3 and 4 | Add scope clarification and better history selection; compare methods on development tasks | Personalization feature, controlled comparisons and documented prompt versions |
| Weeks 5 and 6 | Add long-task splitting, partial progress, interruption recovery and optional solver planning | Demonstration of useful schedule adaptation and scheduling comparison |
| Week 7 | Freeze changes and run the prospective final evaluation | Results with counts, errors, failures, latency and limitations |
| Week 8 | Polish the app and reproduce results; prepare the professor demonstration and report | Working application, data dictionary, evaluation scripts, figures and discussion |

Do not start participant collection in week seven. It should run from the first week onward. If two months have already elapsed, present existing implementations and results honestly and identify this schedule as future work, not completed work.

## What to demonstrate to the professor

1. A vague task receives a useful scope question before estimation.
2. A completed history example changes a later personal estimate, with the exact examples and prediction version inspectable.
3. A five-hour task is split into focus blocks with breaks and correct remaining-work tracking.
4. An interruption triggers replanning without moving finished work or concealing a missed deadline.
5. A benchmark report compares the same cases across rules, generic LLM and personalized LLM, and compares the existing planner with the improved planner.
6. The dataset is documented, real observations are distinguished from synthetic cases, and failed AI calls remain visible in the results.

This produces a defensible software and evaluation contribution. It does not establish a new foundation model, clinical benefit, novel research architecture or guaranteed accuracy improvement. A rigorously documented negative result can still support a substantial project when paired with implemented improvements and reproducible analysis.

## Immediate next implementation

Prioritize reliable task-completion and prediction records, then a small Natural Plan benchmark adapter. These establish the evidence needed to decide whether a model or personalization change helps. Use a modest fixed sample first to stay within free-provider quotas, then expand only after the pipeline and scoring are verified.
