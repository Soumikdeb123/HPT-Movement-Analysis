# Saved analysis history and metric effort

This update combines the history feature from `view-history` (reviewed at
`cd901ad`) with the metric effort calculation and detailed AU explanations from
`new-UI` (`c57e995`). Existing main-branch documentation and platform settings
are retained. The separate account/profile administration changes in
`view-history` are not included.

## Using history

Select **Analysis History** in the analysis page toolbar to list your saved
analyses. Open a record to view its metrics, AU breakdown, charts, annotated
video and export options. **Start a new analysis** clears the current form
without deleting saved results. Deleting an analysis requires confirmation;
running analyses cannot be deleted.

The analysis backend creates `runtime/history.sqlite3` automatically using
Python's built-in SQLite driver. MySQL continues to store accounts; no MySQL
schema migration is required. The authenticated session endpoint also returns
the existing account ID so history has a stable owner. Back up the SQLite file
together with its runtime analysis folders. Run one analysis server process per
runtime directory.

Completed records survive server restarts. Interrupted jobs become failed
records and must be submitted again. Older outputs without persisted ownership
are preserved but are not automatically imported into an account's history.

## Metric effort

The shared live/history result view retains the metric effort formula,
speed/acceleration/braking contributions, valid duration, AU per valid minute,
and explanatory text. See [METRIC_EFFORT.md](METRIC_EFFORT.md) for the formula and
its experimental limitations. AU is not calories, fatigue or a percentage score.

## Validation

- 72 backend tests and 20 Flutter tests passed during integration, including
  history restart persistence, pagination, account isolation, deletion and the
  AU table regression tests.
- A real-service smoke test completed YOLO analysis of a short authorized-video
  excerpt, saved it in history and retrieved the annotated video and reports.
- The user confirmed successful Samsung S22 testing on 18 November 2026.
  Supplied screenshots show completed test1/test4 history entries, metric
  results, AU details, charts and an annotated video.
- Android debug builds were verified using Flutter 3.50 / Dart 3.14, JDK 17 and
  AGP 9.1.1. The dependency lockfile reflects this build environment.

The phone still uses the notebook's auth and analysis services. For USB or
wireless ADB reverse, build with `HPT_AUTH_API_URL=http://127.0.0.1:3000` and
`HPT_ANALYSIS_API_URL=http://127.0.0.1:8000`, then forward both ports for the
selected device. Keep the backend services and the ADB connection running.
Changing networks or restarting may require reconnecting and restoring the
forwarding. This is not phone-local inference or a production deployment.
