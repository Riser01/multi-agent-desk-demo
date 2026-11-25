# Learner Guide — Multi-Agent Desk Demo (v2)

**How Sunday works:** you direct a coding agent. For each phase you paste one prompt, the agent writes the file, and
you check it with `python check.py N`. The instructor demonstrates the same prompts live on screen. Nobody hand-types
code. Watching only is fine too: follow `docs/predict-sheet.md`.

No API key and no account are needed. Everything runs offline on your laptop.

### Words used in this guide (one line each)
- **Terminal:** the window where you type commands (Mac: Terminal; Windows: Command Prompt, called `cmd`).
- **git:** a tool that downloads ("clones") a project and tracks changes. Optional here: the ZIP download works too.
- **venv:** a private Python folder (`.venv`) for this project, so its packages do not mix with anything else.
- **pip:** Python's installer. `pip install -r requirements.txt` installs what this project needs.
- **LangGraph:** a Python library for wiring agents as a graph of steps (nodes) with shared state. The only package we install.
- **Coding agent:** an AI app that edits files and runs commands in your project folder for you (we use Cursor).
- **Stand-in:** the built-in fake model in `llm.py`. Rule-based, free, always gives the same answer, and deliberately easy to fool on `/drill`. It is **not a real model**, and every output says so.
- **Notional cost:** what the same calls would cost at the published list price. You pay nothing; free-tier keys are billed $0.

---

## Setup (do once, before Sunday, about 20 minutes)

### Step 1. Get the project
Repo: **https://github.com/Riser01/multi-agent-desk-demo** (v2 replaces v1 at this address before class; if the link
shows 404, ask your instructor). Pick one option.

**Option A: ZIP (no git needed)**
1. Open the repo page, click the green **Code** button, then **Download ZIP**.
2. Unzip it. Mac: double-click the ZIP in Downloads. Windows: right-click it, **Extract All**, **Extract**.
3. Move the folder to Documents and open it. You should see `README.md`, `check.py` and `AGENTS.md`. If you see one
   more folder inside, open that one: it is the project folder.

**Option B: git**
Check whether git is installed: `git --version`. If it says "not found", install it from
https://git-scm.com/downloads (Windows: accept the defaults; Mac: a pop-up may offer "command line developer tools":
click Install), or use Option A.
```bash
cd ~/Documents
git clone https://github.com/Riser01/multi-agent-desk-demo.git
cd multi-agent-desk-demo
```
Windows `cmd`: use `cd %USERPROFILE%\Documents` for the first line.

### Step 2. Install Python 3.11 or newer
Check first (open a terminal as in Step 3):
- Mac: `python3 --version`
- Windows: `py --version`

You need **3.11 or higher** (3.10 is too old: LangGraph's dependencies need 3.11). If it is lower or "not found":
download Python from https://www.python.org/downloads/, run the installer, and on **Windows tick "Add python.exe to
PATH"** on the first screen. Then close and reopen the terminal and check again.

### Step 3. Open a terminal in the project folder
- **Mac:** open Terminal, type `cd ` (with a space), drag the project folder into the window, press Return.
- **Windows:** open the folder in File Explorer, click the address bar, type `cmd`, press Enter. A black Command
  Prompt window opens already in the folder.
- **In Cursor or VS Code:** open the folder, then Terminal > New Terminal.

**Windows: PowerShell or cmd?** If the prompt starts with `PS C:\...`, you are in PowerShell. Type `cmd` and press
Enter to switch to Command Prompt; every Windows command in this guide is for `cmd`. (In PowerShell the activate
command is `.venv\Scripts\Activate.ps1` and may be blocked by "running scripts is disabled": switching to `cmd` avoids that.)

### Step 4. Create the venv and turn it on
Mac:
```bash
python3 -m venv .venv
source .venv/bin/activate
```
Windows `cmd`:
```bash
py -m venv .venv
.venv\Scripts\activate
```
You should now see `(.venv)` at the start of the line. **Run the second line again in every new terminal** (the venv
switches off when you close the window). With the venv on, `python` means the right Python on both Mac and Windows,
so the rest of this guide just says `python`.

### Step 5. Install LangGraph
```bash
pip install -r requirements.txt
```
This installs `langgraph==1.2.23` and the packages it needs. It takes a minute.

### Step 6. Check the setup
```bash
python check.py
```
What you should see:
```text
Setup  provided CLI, desk, sessions & todo-list.md: all 14 green
AM-1  Two-agent planner + executor (two_agent.py): not built yet (two_agent.py does not exist)
AM-2  Handoff caps + plan check (safety.py): not built yet (safety.py does not exist)
PM-1  Supervisor, workers + reviewer (team.py): not built yet (team.py does not exist)
PM-2  Cost meter, routing + version stamp (prod.py): not built yet (prod.py does not exist)
```
"not built yet" is correct: you build those files on Sunday.

### Step 7. Get the coding agent
We recommend **Cursor**: download from https://cursor.com/download and sign in (a free account works; the free plan
limits how many agent requests you get, so check https://cursor.com/pricing). Any agent that can edit files and run
commands in a folder also works (Claude Code, Copilot, Windsurf); a chat in a browser tab will not.
Open the project folder in it (File > Open Folder) and send this first message:
```text
Read AGENTS.md first and follow its rules. Do not edit provided files or tests. Never open or print my .env file. Wait for my phase prompt.
```

### Step 8 (optional). `.env` for `--live` or `--export langfuse`
Skip this unless you want real Gemini calls (`--live`) or the Langfuse trace viewer. Copy the example file:
- Mac: `cp .env.example .env`, then `open -e .env`
- Windows `cmd`: `copy .env.example .env`, then `notepad .env`

Fill in only the lines you need (no quotes, no spaces) and save. **Windows Notepad warning:** if you create the file
from Notepad's Save As, it may save as `.env.txt`, which is ignored. Use the `copy` command above, or in Save As choose
"All files" and type `.env`. Paste keys only into `.env`, never into the coding agent's chat.

### Step 9 (optional). Langfuse trace viewer
Optional, with your own free account, toy tasks only. Create a project at https://cloud.langfuse.com, make API keys,
and put `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_BASE_URL` in `.env` (US-region projects use
`https://us.cloud.langfuse.com`). Then:
```bash
pip install langfuse==5.2.0
python app.py "Delete the dentist task." --approve no --export langfuse
```
Without keys (or without the package) the same command prints the trace tree in your terminal instead, so
`--export console` always works offline. In the chat, `/export langfuse`, `/export console` or `/export off` switch it.
Prompts and desk text are sent to Langfuse: use the toy desk only. *Honest note: the export is written against
langfuse 5.2.0 and tested offline with a fake recorder; it is not yet verified against a real Langfuse server as of 2026-11-25.*

---

## Where to look (keep this open)
| What | Where | Open it on Mac | Open it on Windows (`cmd`) |
|---|---|---|---|
| Your live to-do list, rewritten after every turn | `todo-list.md` | open it in Cursor, side by side with the terminal (or `open todo-list.md`) | open it in Cursor (or `notepad todo-list.md`) |
| A readable page for the last turn | `out/latest.html` | `open out/latest.html` | `start out\latest.html` |
| The full step log of the last turn | `logs/latest.log` | `open -e logs/latest.log` | `notepad logs\latest.log` |
| One line per turn (what `/monitor` reads) | `logs/runs.jsonl` | `open -e logs/runs.jsonl` | `notepad logs\runs.jsonl` |
| Saved sessions (resume with `python app.py --resume latest`) | `sessions/` | `ls sessions` | `dir sessions` |

Every log, `runs.jsonl` row and HTML page says `mode: offline stand-in (not a real model)` unless you used `--live`.

---

## Warm-up: the built-in single agent (Week 6)
```bash
python app.py
```
Type `Add Buy milk`, then `/desk`, then `/quit`. Expected:
```text
INFO  [single] sees: goal + whole desk + full notes (357 chars); tools: all 8
INFO  [single] model=stand-in in=141(est.) out=21 (0.01s)
INFO  [single] tool add_task -> ok: added task #9: Buy milk
status: done  |  calls: 1  |  answer: added task #9: Buy milk
```
`Buy milk` appears in `todo-list.md`. `/quit` saves; `python app.py --resume latest` brings the same desk back.
The stand-in has no chat memory: name the task or event in every message.

---

## How every phase works
1. Paste the phase prompt into your coding agent. Approve its file edits.
2. Run `python check.py N` until it is green, then `python check.py` to confirm nothing earlier broke.
3. Try it live in `python app.py` and compare with "Expected" below.
4. If a check line fails, paste only its `requirement:` line to the agent and say "fix only this".

---

## Morning — Build Hour 1: Two-Agent System

### AM-1: Planner + Executor (`two_agent.py`, 30 min)
**What you learn:** split "decide" from "do". The planner has no tools; the executor runs the plan through the delete gate.
**Prompt to your coding agent:**
```text
Read AGENTS.md and docs/AM-1.md, then build two_agent.py. Run python check.py 1 until green.
```
**Expected check:** `AM-1  Two-agent planner + executor (two_agent.py): all 5 green`
**Try it live:** `python app.py --setup two`
- Type `Add File taxes, then show me my list.` -> `File taxes` appears in `todo-list.md`:
  ```text
  INFO  [planner] sees: goal + desk notes (46 chars, not capped); tools: none
  INFO  [planner] proposed 2 step(s): ['add_task', 'list_tasks']
  INFO  [executor] sees: the plan only (2 step(s)), never the notes; tools: all 8 through the [y/N] gate
  status: done  |  calls: 1  |  answer: add_task: added task #9: File taxes | ...
  ```
  `calls: 1`: only the planner calls the model; the executor just runs tools.
- Type `Delete the dentist task.` -> answer `n` at `[y/N]` -> `status: done-with-denials`, the task stays.

### AM-2: Break It & Cap It (`safety.py`, 30 min incl. Your turn)
**What you learn:** a planted note can steer a planner; two plain-code barriers stop it.
1. **Watch the attack (unguarded).** In `python app.py --setup two`, type `/drill`, then `Tidy up my tasks.`. The
   planner obeys the note and wants to delete task 1:
   ```text
   GATE [approval needed] executor wants to DELETE task #1: 'Pay rent'
     Allow this irreversible action? [y/N]:
   ```
   **Answer `n`.** Pay rent stays (`status: done-with-denials`). Optional: `/reset`, `/drill`, `Tidy up my tasks.` again
   and answer `y` once to see what an unguarded delete looks like: Pay rent disappears from `todo-list.md`. Type `/reset`.
2. **Prompt to your coding agent:**
   ```text
   Read AGENTS.md and docs/AM-2.md, then build safety.py. Run python check.py 2 until green.
   ```
   **Expected check:** `AM-2  Handoff caps + plan check (safety.py): all 5 green`
3. **Your turn (8 min):** make `validate_plan()` also reject two identical steps (same tool and same args).
   - Coding agent prompt: `In safety.py validate_plan(), reject any plan where two steps have the same tool and args, and return a plain-English reason naming the step. Run python check.py 2 your-turn.`
   - Expected: `AM-2  Your turn: duplicate-step rule (optional exercise): all 2 green`
   - Watch-only: write the rule in one sentence, plus one plan that must fail and one that must pass.
4. **Re-test the attack:** `/drill` -> `Tidy up my tasks.`:
   ```text
   WARN  [handoff] cap context cut to 600 chars
   INFO  [planner] sees: goal + desk notes (612 chars, capped); tools: none
   INFO  [planner] proposed 1 step(s): ['list_tasks']
   status: done  |  calls: 1
   ```
   No gate question: the cap removed the override before the planner read it, and Pay rent stays. `validate_plan()`
   is the second barrier if a delete still slips through (`status: plan-rejected`).

---

## Afternoon — Build Hour 2: Multi-Agent Team & Production

**Join here if the morning is unfinished** (this overwrites `two_agent.py` and `safety.py`; copy your own versions
somewhere safe first if you want to keep them):
- Mac: `unzip -o checkpoints/after-AM.zip`
- Windows `cmd`: `tar -xf checkpoints\after-AM.zip`

then `python check.py` (Setup, AM-1, AM-2 green).

### PM-1a & PM-1b: Supervisor, Workers & Reviewer (`team.py`, 40 min = 20 + 20)
**What you learn:** route work to specialists that hold only their own tools (least privilege), then add a reviewer
in front of the human gate (defence in depth), and see what it costs in model calls.
- **Part A prompt (20 min):**
  ```text
  Read AGENTS.md and docs/PM-1.md Part A, then build supervisor + tasks_worker + calendar_worker in team.py.
  ```
  Test in `python app.py --setup team`: `Cancel the team sync on Wednesday and remind me to email Anil.`, answer `y` at the gate:
  ```text
  INFO  [supervisor] -> calendar: ...
  INFO  [calendar] sees: task + calendar only (143 chars); tools: add_event, list_events, cancel_event
  INFO  [supervisor] -> tasks: ...
  INFO  [tasks] sees: task + tasks + full raw notes (280 chars); tools: add_task, list_tasks, complete_task, delete_task
  INFO  [supervisor] -> finish: All requested desk actions processed.
  status: done  |  calls: 5
  ```
  Each worker can only use its own tools. Note the tasks worker still reads the raw notes (least privilege limits tools, not data).
- **Part B prompt (20 min):**
  ```text
  Read docs/PM-1.md Part B, add reviewer_node (max 2 rounds) to team.py, and run python check.py 3 until green.
  ```
  **Expected check:** `PM-1  Supervisor, workers + reviewer (team.py): all 9 green`
  Test: `/reset`, `/drill`, `Tidy up my tasks.` with `/review off` and answer `y`: Pay rent is deleted (the team has no
  cap). Then `/reset`, `/review on`, `/drill`, `Tidy up my tasks.`:
  ```text
  WARN  [reviewer] rejected round 1: User goal did not ask for an irreversible delete/cancel.
  WARN  [reviewer] rejected round 2: User goal did not ask for an irreversible delete/cancel.
  status: done-with-denials  |  calls: 7
  ```
  No `[y/N]` question: the reviewer stopped it first. (The stand-in always answers round 2 like round 1.)

**Join here if PM-1 is unfinished:** Mac `unzip -o checkpoints/after-PM1.zip`, Windows `tar -xf checkpoints\after-PM1.zip`,
then `python check.py` (everything up to PM-1 green).

### PM-2: Cost Meter, Routing, Rollback & Comparison (`prod.py`, 35 min incl. Your turn)
**What you learn:** measure notional cost per task, route routine steps to a cheaper model, stamp every run with a
release version, and enforce a hard cost ceiling in code.
**Prompt to your coding agent:**
```text
Read AGENTS.md and docs/PM-2.md, then build prod.py. Run python check.py 4 and python check.py until all green.
```
**Expected check:** `PM-2  Cost meter, routing + version stamp (prod.py): all 5 green`, and `python check.py` all green.
- **Your turn (8 min):** in `python app.py --setup team --review`: `/reset`, `/ceiling 0.00001`, then
  `Cancel the team sync on Wednesday and remind me to email Anil.`:
  ```text
  status: cost-ceiling  |  calls: 1  |  answer: cost ceiling reached: $0.000018 is over $0.000010 (notional)
  ```
  It stops on the first call, before `Team sync` is cancelled. `/ceiling off` to clear it.
- **Production tour (last 10 min):**
  - `/rollback` — switches the release label `stable 1.0.0` <-> `canary 1.1.0` (shown in `todo-list.md`). The prompt
    hash stays the same, because prompts and routing did not change.
  - `/monitor` — reads `logs/runs.jsonl`: run count, median and max notional cost, `ALERT stopped/capped runs`.
  - `/compare` — runs `single`, `two`, `team`, `team-review` on fresh copies of the desk (your desk is untouched):
    ```text
    setup        calls  cost($, notional)  S1-add  S2-cancel          S3-drill (safe?)
    single           3           0.000359  done    done-with-denials  DELETED (done)
    two              3           0.000290  done    done-with-denials  SAFE (done)
    team            11           0.000234  done    done-with-denials  DELETED (done)
    team-review     16           0.000504  done    done-with-denials  SAFE (done-with-denials)
    ```
    Illustrative only: stand-in tokens are estimates. Run with `--live` for real numbers.

---

## Optional stretch (harder): a real `interrupt()` approval gate
Read `docs/stretch.md`. Prompt: `Read AGENTS.md and docs/stretch.md, then build stretch.py. Run python check.py stretch until green.`
Then `python stretch.py "Delete the dentist task."` pauses the graph, saves it, asks you, and resumes.

---

## Stuck ladder
1. Paste the failing `requirement:` line from `python check.py` to your agent: "Fix only this requirement."
2. Still red after 2 tries: copy the finished file and read it with your agent.
   - Mac: `cp solution/two_agent.py .` (or `safety.py`, `team.py`, `prod.py`)
   - Windows `cmd`: `copy solution\two_agent.py .`
3. `(.venv)` missing from the prompt, or "No module named langgraph": run the activate line from Step 4, then `pip install -r requirements.txt`.
4. Watch-only / phone learners: follow `docs/predict-sheet.md` and watch `todo-list.md` on screen.

## Quick reference
| Phase | File | Check | Expected |
|---|---|---|---|
| Setup | provided | `python check.py 0` | 14 green |
| AM-1 | `two_agent.py` | `python check.py 1` | 5 green |
| AM-2 | `safety.py` | `python check.py 2` | 5 green |
| AM-2 Your turn | `safety.py` | `python check.py 2 your-turn` | 2 green (optional) |
| PM-1 | `team.py` | `python check.py 3` | 9 green |
| PM-2 | `prod.py` | `python check.py 4` | 5 green |
| Stretch | `stretch.py` | `python check.py stretch` | 5 green (optional) |
| All | | `python check.py` | every built phase green |
