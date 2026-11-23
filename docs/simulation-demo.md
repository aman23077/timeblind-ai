# Synthetic demonstration cohort and measured software checks

This demonstration uses 19 generated profiles P001–P019, not the email list supplied for recruitment. No real people are enrolled, given invented demographics, or assigned invented consent or reviews. The local application database is populated through its existing SQLAlchemy models; actual participant records remain unchanged. Human pilot totals exclude accounts marked synthetic even if research consent is accidentally enabled later.

## Run locally

From the repository root:

```powershell
C:\Python314\python.exe -m scripts.seed_pilot_simulation
```

The script backs up the existing local SQLite database first. It inserts only the labelled simulation cohort and archives its monitors. It creates no credentials, login sessions, pairing tokens for use, notifications, or study enrollment. The generator uses a fixed seed, stable UUIDs and a dataset marker; running it again reuses existing simulation records and does not duplicate or overwrite them. The JSON report is recalculated from persisted records.

The default seed writes the local timeblind_ai.db, not the hosted PostgreSQL database. To populate the same labelled cohort on the hosted database, after deploying the matching code:

```powershell
C:\Python314\python.exe -m scripts.seed_pilot_simulation --postgres --output output/simulation/hosted
```

Enter the External Database URL at the hidden prompt and explicitly confirm `SEED SYNTHETIC`. Do not paste credentials into chat, command arguments, source code or Git. PostgreSQL writes use a transaction; the command adds only simulation accounts and refuses to reuse an account without the expected provenance marker. No deletion or reset of the database is performed.

## Dashboard and existing APIs

Open `/admin/simulation` while signed in with an existing administrator account. The JSON endpoint is `/api/v1/admin/simulation`. The dashboard queries the connected database and does not hardcode the reported counts. A local seed will not appear on Render until the hosted database has separately been seeded.

The ordinary admin browser, source-filtered dataset export, per-user insights and activity summary endpoints can retrieve the same records. `/study/admin` remains for human pilot results. The new simulation dashboard is separate and explicitly labelled; do not add these figures to the participant cohort.

The generated cohort contains 152 tasks, including 95 completed, 19 unfinished, 19 missed and 19 pending. It stores 114 session fixtures, 19 schedules and 4,104 synthetic activity intervals. The intervals are only short generated excerpts, not a complete measurement of desktop use or attention. Each profile has a computed deterministic summary; there are no participant reviews and no LLM-generated reviews.

## Metrics and assumptions

Synthetic duration outcomes are generated independently of rules predictions from category workload assumptions, a profile-speed factor, difficulty, lognormal variation and interruptions. Personal guesses are generated for demonstration only. No actual student behavior was observed, and generator constants do not establish population distributions.

Rules duration predictions come from the production deterministic decomposer. MAE, bias, actual-denominator MAPE, category results and the within-15-minute proportion are calculated from completed synthetic tasks. These metrics depend on the simulation assumptions. The computed summaries are not a separate AI review model and must not be described as participant-rated recommendations.

The scheduler calls the production rules planner. The demo dashboard checks non-overlap and positive duration for its generated schedules. A separate stronger benchmark exercises 23 policy scenarios and 12 scheduler scenarios with 146 specified checks:

```powershell
C:\Python314\python.exe -m scripts.synthetic_benchmark --output output/simulation/benchmark
```

Do not combine its 60 held-out simulated duration rows with the demo's 95 completed tasks or present their scores as the same experiment.

## Optional real provider check

The separate `scripts.check_simulation_ai` command makes one to three real provider requests on labelled synthetic task descriptions and records current success/failure, latency and predictions. Actual duration and generated personal guesses are not included in the prediction inputs. It is a tiny integration check, not human accuracy evaluation, and consumes quota. Set the provider configuration locally and enable LLM planning before running it. It does not call the provider merely by rerunning the seeder.

## Report wording

“We populated a labelled synthetic demonstration cohort of 19 profiles and 152 tasks to exercise persistence, scheduling, activity summaries and analytics. Ninety-five completed synthetic tasks yielded rules MAE of 11.93 minutes and 69.47% within 15 minutes under the specified generator. Separately, all 146 specified synthetic policy/scheduler checks passed. These findings demonstrate behavior under simulated inputs and do not establish human usability, clinical validity or real-world productivity improvement.”

Use actual live-call results only after checking the saved run artifact. Human pilot participation, usefulness ratings, recommendation acceptance, observed attention and measured time lost to switching remain unmeasured by this simulation. No TDI diagnosis or fabricated human rating is inferred from these records.
