# Phase W7-5 (stretch, in `extras/`): parallel workers with `Send`, and why the reducer matters

Not built in class. Read and run `extras/fanout.py`; it is self-contained.

## The concept
When parts of a goal do not depend on each other, the workers need not wait for each other. A conditional edge can return `[Send("worker", {...}), Send("worker", {...})]`: LangGraph runs the node once per `Send` in the same step, and the next node runs once when all are done (the aggregator). Two rules make it safe:
- **A reducer** on every key the parallel workers write (`Annotated[list, operator.add]`). Without it LangGraph refuses with `InvalidUpdateError`.
- **One writer at a time** on the shared world: a lock around the gate call, so two workers cannot hand out the same id.

Quota safety: the default runs the parts one after another; `--parallel` fans out. `--delay` adds **simulated** latency so the time saving is visible offline.

## Run it
```bash
python extras/fanout.py --parallel --delay 0.5
python extras/fanout.py --delay 0.5 --quiet
python extras/fanout.py --no-reducer
python check.py extras
```
What you should see (`sample-runs/09a`, `09b`, `09c`):
```text
seconds: 0.56 (includes SIMULATED latency)          <- parallel, two parts
seconds: 1.07 (includes SIMULATED latency)          <- one after another
ERROR ... [graph     ] error   InvalidUpdateError: At key 'results': Can receive only one value per step. ...
status: no-reducer
```

## What you learn
Parallel saves wall-clock time, not tokens. It needs a merge rule (the reducer) and a rule for the shared world (the lock), and it spends quota in bursts.
