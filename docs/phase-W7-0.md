# Phase W7-0: why one agent breaks (5 min, nothing to build)

## The concept
Last week's Desk Assistant had three tools. It has grown: tasks, a calendar and notes, **twelve tools**, several of them look-alikes (archive, delete and clear_done; complete and rename; two kinds of list). One agent now carries the whole twelve-tool menu in **every** call, and must pick the right look-alike every time. Two costs grow with the tool count: tokens per call, and the chance of picking the wrong tool. Before splitting anything into a team, measure the thing you would split.

## What you build
Nothing. `baseline.py` is provided: last week's loop, now with all twelve tools.

## Run it
The offline stand-in routes correctly. Watch the **input tokens per call**:
```bash
python baseline.py "Add a dentist appointment on Fri 27 Nov 10:00 and add a task to buy a gift for Anil." --approve no
```
What you should see (from `sample-runs/00b-baseline-offline-two-parts.txt`):
```text
INFO  +  0.00s  [agent     ] model   stand-in replied in 0.00s (401 in / 22 out tokens, est.): {"tool": "add_event", ...}
INFO  +  0.00s  [agent     ] model   stand-in replied in 0.00s (431 in / 15 out tokens, est.): {"tool": "add_task", ...}
INFO  +  0.00s  [run       ] run     ended: status=done after 3 model calls, 1285 in / 79 out tokens (est.), 0.0s
```
About 400 input tokens per call (estimated), most of it the twelve-tool menu, paid again on every call.

Now a **replayed** failure shape. This file was written by hand (it says so in every line): with twelve similar tools, the agent picks `delete_task` for an "archive" request, the gate stops it, and then the agent claims success anyway.
```bash
python baseline.py "Archive the dentist task." --mode replay --replay data/replays/w7-0-misroute.json --approve no
```
What you should see (`sample-runs/00a-baseline-replayed-misroute.txt`):
```text
INFO  ... run     start baseline  mode=replay (REPLAYED (scripted): written by hand to show a known failure shape ...
WARN  ... [agent     ] gate    delete task 4: "Book dentist appointment"  ->  denied
status: done-with-denials
answer: Done: the dentist task is archived.
```
The answer is false: the task is not archived (look at the list). The gate saved the task; nothing checked the claim.

With your own key you can see what a real model does today (it may route cleanly: that is a valid result, write it down):
```bash
python baseline.py "Archive the dentist task." --approve ask --live
```
Then open `out/latest.html` in a browser.

## What you learn
- One agent pays for its whole tool menu on every call.
- Look-alike tools invite the wrong pick; the gate catches irreversible ones, nothing catches the rest.
- A replayed run is labelled; a live run is the only evidence about today's model.

## Common mistakes
- Treating the replay as a live result. It is a scripted shape, labelled REPLAYED.
- Concluding "the model is bad". The point is the *design*: twelve tools in one prompt is a load you chose.
