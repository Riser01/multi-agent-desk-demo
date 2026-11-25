# Rules for your coding agent

1. Do NOT edit provided files (`app.py`, `desk.py`, `llm.py`, `check.py`, `data/seed.json`) or any file in `tests/`.
2. Do NOT read or copy from `solution/` unless the learner explicitly asks you to.
3. Build ONLY the phase file requested (`two_agent.py`, `safety.py`, `team.py`, `prod.py`, or the optional `stretch.py`).
4. Keep code simple, readable, and well-commented: a top docstring that says what the file is, why it is needed, what
   goes wrong without it and what to look at in the log. Python 3.11+ standard library + LangGraph only; no new pip packages.
5. Always verify by running `python check.py N` (and `python check.py` at the end). Never open, print or ask for `.env`
   or any API key.
