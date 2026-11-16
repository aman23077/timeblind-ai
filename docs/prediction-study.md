# BTP prediction study

Copy the blank template to a private CSV. Use one row per real task and pseudonymous IDs. Keep task descriptions and results containing personal information out of Git.

## Before starting each task

1. Record a unique task ID, a consistent user ID, concrete scope, task type, and difficulty. Record the user's estimate before showing any automated estimate.
2. Save the current TimeBlindAI rules estimate and the LLM estimate and range for the same scope. Collect the rules estimate with LLM planning disabled and without passing the user estimate as a starting value. Use the same input convention for the LLM. Record the Git revision, provider, model, and configuration in your study notes. Freeze those settings for the study.
3. Mark the LLM call as ok, failed, or not_run. For failed and not_run, leave all three LLM number fields blank. An AI fallback counts as failed if a call was attempted. Save predicted_at with its UTC offset after collecting the predictions and before starting work. For example, 2026-11-13T16:00:00+05:30.
4. Keep the original predictions. If the scope changes substantially, mark the original task as unfinished and log the revised task separately before work starts on it. Keep an audit note of such exclusions.

## After completing each task

Record completed_at with its UTC offset. Enter actual_minutes as the sum of focused work across sessions, excluding breaks and unrelated work. Leave both completion fields blank while unfinished. Use a dot as the decimal separator if recording partial minutes.

Aim for 30 to 50 completed tasks for the first study. Use the same tasks for each baseline and record provider failures as they happen. Try the procedure on practice tasks first, then freeze the protocol and collect fresh evaluation tasks.

## Run the evaluator

From the repository root in PowerShell:

    py -m scripts.evaluate_prediction_log "$env:TEMP/timeblind-predictions.csv" --init
    py -m scripts.evaluate_prediction_log "$env:TEMP/timeblind-predictions.csv" --out "$env:TEMP/timeblind-results.json"

The first command creates a blank log. Run the second after entering completed tasks. The script runs offline and uses only the Python standard library.

## Scoring rules

- Primary metric is mean absolute error in minutes. Also report median absolute error and the percentage within 15 minutes of actual time, inclusive.
- Calibration multiplies the logged rules estimate by the median actual-to-rules ratio from prior tasks of the same user, task type, and difficulty. It requires three matching tasks completed strictly before the prediction timestamp. Until then it uses the original rules estimate. This is an offline replay of the proposed calibration.
- The full-cohort AI-plus-fallback score uses the logged LLM estimate on success and the logged rules estimate otherwise. If some LLM calls were skipped, this measures the recorded mix of AI and rules. Attempt every task for a full-cohort test of the AI-enabled policy.
- Compare standalone LLM accuracy and the other methods on the same successful rows. Report LLM success rate over attempted calls and range coverage over successful calls. Report skipped calls and unfinished tasks separately.
- Schedule ordering needs a separate paired benchmark with identical durations, windows, breaks, deadlines, dependencies, and events. Count hard constraint violations, high-priority tasks scheduled, and deferred tasks for each variant.
