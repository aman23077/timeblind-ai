# Administration and reproducible synthetic evaluation

Open http://localhost:3000/admin and sign in as **aman23077@iiitd.ac.in** with that account's password. The page shows the signed-in account and provides a Switch account button if you are using a different one. The old account ending in 23076 has no administrator grant. Password setup/reset accepts the existing recovery key and the target email. Restart the backend after updating the code so it loads the new routes and tables.

The admin page lists users and paginated tasks/sessions. Select a user, then choose a dataset table to inspect full records, including app intervals, reminders, policy decisions, schedule revisions, dependencies and context. ZIP downloads contain linked CSV tables and a manifest. You can download all accounts, the selected account, or only synthetic accounts. Login and pairing credentials are excluded. The API enforces admin access independently of the page.

Existing accounts have **unverified** provenance. These records cannot automatically be treated as measured human training data. Each exported row includes provenance, account ID, dataset ID and the account's research-consent setting. Exporting data does not confer consent to train or publish it. Review identifying task text and URLs before sharing. Spreadsheet-formula prefixes in text are escaped with an apostrophe.

## Test account and files

- Email: `timeblind-btp-test@example.com`
- User ID: `c9ab358f-f887-5c1d-8457-b90ec725c6e5`
- Dataset ID: `btp-synthetic-v1`
- This is an ordinary test account. View its entries while signed in as the administrator.
- Its random password is printed once on initial creation. Reruns preserve the password. Use the existing password-recovery flow if needed.

Run from the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m scripts.synthetic_benchmark
```

This creates files in `data/evaluation/synthetic/` and evaluates the actual production functions in isolated in-memory databases. It does not make external AI calls or modify your app database.

To also populate the local test account:

```powershell
.\.venv\Scripts\python.exe -m scripts.synthetic_benchmark --seed-account
```

Seeding is additive and idempotent for a fixed dataset version. Existing records and passwords are preserved. Use the default seed 23077 when seeding this version. For alternative random seeds, use a separate output directory without `--seed-account`. The account holds 300 simulated completed tasks/sessions plus archived scenario examples. Scenario monitors and adaptive plans are disabled, sessions are closed, and nudges are resolved so old scenarios cannot trigger reminders when you log in. Original scenario states and labels remain in the artifact CSVs.

Artifacts:

| File | Use |
|---|---|
| `tasks.csv` | 300 duration examples with targets, predictions, participant IDs and splits |
| `model_inputs.csv` | Task inputs without actual durations or rule predictions |
| `model_predictions_template.csv` | Fill with genuine model predictions or explicit failures |
| `scenarios.json` | 23 labeled policy scenarios and 12 scheduler scenarios |
| `scenario_records/*.csv` | Executed scenarios, including raw two-second telemetry, decisions and schedule blocks |
| `report.json` | Metrics, per-case pass/fail, constraint checks and external-model results |
| `report.md` | Report-ready summary with interpretation limits |
| `manifest.json` | Seed, provenance and SHA-256 hashes of benchmark inputs |

## Duration experiment

The simulator uses five task types, three difficulty levels, task quantity, participant-specific speed, lognormal duration noise and occasional interruptions. Workload rates are independent constants in `duration_rows`, not measured facts. Simulated duration is generated before invoking the app estimator. Synthetic outcomes are therefore a controlled experiment under these assumptions, not ground truth about humans.

There are 15 simulated profiles. Profiles 0–8 supply 180 training rows, 9–11 supply 60 validation rows, and 12–14 supply 60 test rows. Profiles never cross splits. All these profiles are stored under one test account for inspection, so use `simulated_participant_id` and `split` from the artifact, not the database owner, to train and evaluate.

The current benchmark compares the app's duration rules with a simple trained baseline: median actual/rules ratios grouped by task type and difficulty, fitted on training rows only. This baseline is an experiment and does not change production personalization. Report MAE in minutes, median absolute error and the proportion within 15 minutes on the same 60 test tasks. Use validation data for tuning and keep the test set untouched during model development.

For another estimator or LLM, provide columns `model,task_id,status,predicted_minutes`. Use `status=ok`, `failed`, or `not_run`. Feed only permitted input features to the model. Never include `actual_minutes`, completion timestamps, session outcomes, scenario labels or the entire target CSV in its prompt. Record provider/model version, prompt version, generation settings, latency and run date separately.

```powershell
.\.venv\Scripts\python.exe -m scripts.synthetic_benchmark --predictions path\to\predictions.csv --output data\evaluation\model-comparison
```

The evaluator reports prediction coverage and compares model and rules on the same successfully predicted test tasks. Failed or missing predictions do not count as model successes. Compare models on common task IDs or report coverage alongside error. No LLM accuracy is claimed by the default run.

## Policy labels and scheduling checks

Labels encode expected rule behavior, not a diagnosis of distraction. App switching can be necessary work and idle input can mean reading or thinking.

- A sustained app run lasts at least 6 seconds. Count app changes between sustained runs no more than 5 seconds apart within a rolling 5-minute window. Four changes trigger a switch nudge.
- Activity nudges require at least 60% observed coverage and a monitor update within 15 seconds. Disabled, disconnected or mostly unknown monitoring must suppress them.
- Idle nudges require at least 120 seconds of trailing observed idle time. Short active interruptions and unknown periods break an idle run.
- Slippage requires both at least 5 minutes overrun and an overrun/planned-duration ratio of at least 0.20.
- Reminder boundaries are 5 minutes before a planned start and at least 5 minutes late.
- Candidate priority is slippage, late start, context switches, idle, upcoming. Emit at most one nudge per evaluation. Global cooldown is 10 minutes, or 20 for minimal nudge preference. Evaluation is throttled to 30 seconds. There is no snooze action.
- Scheduler checks cover remaining-window bounds, overlaps, event conflicts, deadlines, dependencies, completed-task removal, active-session preservation, remaining-time forecasts, capacity deferrals and unchanged-input stability.

`static_past_starts` is measured by building a frozen baseline plan beginning 20 minutes before the simulated disruption. `adaptive_past_starts` counts past starts after replanning. This narrow comparison does not measure global schedule optimality or user productivity.

The initial 146 checks passed on 35 hand-authored scenarios. The 100% policy label agreement means these specified scenarios conform to the rules. It is not 100% behavioral detection accuracy. Scheduler feasibility is not proof of an optimal schedule. Expand scenarios and vary workload distributions before using these as a broad benchmark.

## Next evidence for the BTP report

Use this benchmark for regression and ablations. Next collect consented, prospective prediction logs before each real task, plus actual completion times and optional monitoring. Obtain participant labels for whether a nudge was useful, inappropriate, or unnecessary. Compare no nudges, fixed reminders and adaptive policies with a counterbalanced participant study. Report task completion rate, deadline misses, estimation error, false nudges per hour, nudge acceptance/dismissal and participant feedback. Split real participants across training and testing, report sample sizes and uncertainty, and keep synthetic results separate from human results.
