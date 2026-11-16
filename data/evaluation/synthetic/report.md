# Synthetic benchmark

Synthetic simulation only. No human outcomes measured.

Seed: 23077. Duration records: 300. Profiles: 15 (9 train, 3 validation, 3 test).
Policy scenarios: 23. Scheduler scenarios: 12. Checks: 146/146.

| Duration baseline (held-out profiles) | N | MAE (minutes) | Within 15 minutes |
|---|---:|---:|---:|
| rules | 60 | 40.05 | 28.33% |
| train_calibrated_rules | 60 | 25.81 | 46.67% |

Policy metrics: {"cases": 23, "exact_label_accuracy": 1, "precision": 1.0, "recall": 1.0, "false_positive_cases": 0, "false_negative_cases": 0}

These cases test conformance to specified rules and constraints. They do not establish real-world distraction detection, productivity gains, or optimal scheduling.
No LLM was called by this script. External prediction results, when supplied, are in report.json.

See docs/synthetic-evaluation.md for generator assumptions, label definitions and evaluation protocol.
