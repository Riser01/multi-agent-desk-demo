# Predict sheet (the no-code path, and a good habit for everyone)

Give each row about 3 minutes. Before each run, write what you think will happen: how many model calls, which agents speak, the final status, and what changes on the desk. Then run it (or open the recorded run in `docs/sample-runs/`) and compare. If you cannot code, this sheet plus the recorded runs is a complete way through the day.

| Phase | The run (3 min per row) | Predict: calls? status? what changes? | Recorded run (`.txt`; `.html` where shown) |
|---|---|---|---|
| W7-0 | one agent, twelve tools, "add a dentist appointment and a gift task" | | `docs/sample-runs/00b-baseline-offline-two-parts.txt` |
| W7-0 | REPLAYED: "Archive the dentist task", human says no | | `docs/sample-runs/00a-baseline-replayed-misroute.txt` |
| W7-1 | one agent node: "Add File taxes, then show me my list" | | `docs/sample-runs/01a-single-add-and-list.txt` + `.html` |
| W7-2 | planner + executor, the same goal. Fewer or more tokens than W7-1? | | `docs/sample-runs/02a-two-agent-add-and-list.txt` + `.html` |
| W7-3 | planted note, human clicks yes to everything | | `docs/sample-runs/03a-injection-plan-rejected.txt` + `.html` |
| W7-3 | 1,500-character note on the desk | | `docs/sample-runs/03b-huge-note-capped.txt` |
| W7-4 | supervisor + workers, calendar and task in one request. How many calls? | | `docs/sample-runs/04a-team-two-domains.txt` + `.html` |
| W7-4 | planted note + blind yes, no reviewer. Is anything deleted? | | `docs/sample-runs/04b-team-planted-note-no-reviewer.txt` |
| W7-6 | the same, with the reviewer | | `docs/sample-runs/06a-reviewer-blocks-planted-note.txt` + `.html` |
| W7-6 | "Delete the dentist task", reviewer approves, human says no | | `docs/sample-runs/06b-reviewer-approves-human-refuses.txt` |
| W7-7 | ceiling $0.0001: where does the run stop? | | `docs/sample-runs/07b-cost-ceiling-stops.txt` |
| drill | "Cancel the team sync and tidy up my list": does the plan check stop the planted-note deletes? | | `docs/sample-runs/10a-drill-cancel-as-consent.txt` |
| W7-8 | which setup is cheapest, which passes most, and why? | | `docs/sample-runs/08a-compare-offline.txt` + `.html` |

You "win" a row when you predicted the kind of outcome (the status, whether the desk changed, roughly how many calls), not the exact words.
