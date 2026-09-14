# TimeBlindAI Baseline Model Report

## Dataset
- Exported task rows: 46
- Supervised rows with estimate and actual time: 33
- Train rows: 26
- Test rows: 7

## Estimation Behavior
- Average estimate error: 51.09 minutes
- Median estimate error: 18.00 minutes
- Overruns: 17
- Underruns: 16
- Robust actual/estimated ratio used by baseline: 1.131

## Baseline Prediction Results
- Raw user estimate MAE: 68.00 minutes
- Global ratio predictor MAE: 69.71 minutes
- Task type + difficulty predictor MAE: 68.14 minutes

## Learned Group Ratios
- assignment / easy: 0.789x
- assignment / medium: 0.735x
- reading / medium: 1.524x
- study / easy: 1.935x
- study / hard: 1.135x

## What This Proves
This is not the final model. It proves that TimeBlindAI can collect supervised planning data and evaluate whether personalization improves duration prediction over a raw user estimate.
