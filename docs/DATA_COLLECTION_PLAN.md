# TimeBlindAI Data Collection Plan

## Goal

Collect at least 50 completed task records that connect a user's planned estimate with the actual time taken.

This gives us the first supervised dataset for a duration prediction model.

## What Counts As One Good Entry

One useful row needs:

- Task title
- Task type
- Difficulty
- Estimated minutes
- Actual completed minutes
- Feedback after completion

The most important pair is:

```text
estimated_minutes -> actual_minutes
```

That is what the first model learns from.

## Suggested 50 Entry Mix

Use real or realistic tasks. Do not make all tasks the same.

- 10 coding/debugging tasks
- 10 writing/report tasks
- 10 study/revision tasks
- 10 admin/personal tasks
- 10 mixed tasks such as research, reading, design, planning, chores

For each category, include easy, medium, and hard tasks.

## Good Examples

```text
Title: Fix login redirect bug
Type: coding
Difficulty: hard
Estimate: 45
Actual: 80
Feedback: longer_than_expected
Reason: harder than expected
Notes: debugging took longer because the session state was confusing
```

```text
Title: Revise DBMS joins
Type: study
Difficulty: medium
Estimate: 30
Actual: 35
Feedback: as_expected
Reason: already familiar with it
Notes: small delay but mostly accurate
```

## Bad Entries

Avoid rows like:

```text
Title: Work
Estimate: 60
Actual: blank
```

or:

```text
Title: Assignment
Type: generic
Difficulty: medium
Estimate: 30
Actual: 30
```

Too many identical clean rows make the model look fake and teach it almost nothing.

## After Entry Collection

Run:

```bash
python scripts/export_training_data.py
python scripts/analyze_training_data.py
```

Outputs:

```text
data/training/timeblind_training_data.csv
data/training/model_baseline_report.md
```

## What We Can Claim

After 50 entries, we can honestly say:

```text
We implemented a data collection pipeline for time-blind task planning and created a first supervised dataset. We exported task/session history into a training CSV and evaluated baseline duration prediction methods using estimation error and mean absolute error.
```
