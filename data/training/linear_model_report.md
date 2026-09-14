# TimeBlindAI Linear Regression Report

## Dataset
- Supervised rows: 31
- Train rows: 24
- Test rows: 7

## Result
- Raw estimate MAE: 43.00 minutes
- Linear regression MAE: 29.27 minutes

## Features Used
- estimated_minutes
- quantity_value
- completed_session_count
- has_deadline
- task_type=assignment
- task_type=meeting_prep
- task_type=reading
- task_type=study
- task_type=writing
- difficulty=easy
- difficulty=hard
- difficulty=medium

## What This Means
This is the first trainable ML model for TimeBlindAI. It predicts actual task duration from structured task data. With the current small dataset, the result should be treated as a proof of pipeline, not a final accurate model.
