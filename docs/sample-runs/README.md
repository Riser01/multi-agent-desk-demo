# Recorded runs

Every file here is a real recorded run of the command in its header, made on 2026-11-24 with the **offline stand-in** (`stand_in.py`): a rule-based fake, deliberately gullible, not a real model. Token counts are estimates (characters / 4) and costs are notional. Files whose header says `mode=replay (REPLAYED (scripted) ...)` play a hand-written failure shape, never a live model.

The header also says which learner files existed when it was recorded (for example "built up to W7-3"), so the output matches what you see at that point in the day. Times and file names differ on your machine.

Seven runs also have the HTML report page saved next to them (`01a`, `02a`, `03a`, `04a`, `06a`, `07a`, `08a` = `out/compare.html`): open them in a browser.

No live-model runs are recorded here yet. Record your own with `--live --record data/replays/<name>.json`.
