"""The desk: the to-do list, the calendar and the notes, plus the twelve tools that change them. PROVIDED.

This is last week's output, carried forward. In Week 6 you built three tools (add, list, delete) with a risk tier, an
input check and plain words for the approval question. The Desk Assistant has since grown: it now keeps a calendar
and notes too, and has twelve tools. Twelve similar tools in one prompt is exactly the pain that makes people split
one agent into a team, so the tools are given to you and this week is about the team around them.

The desk is the WORLD the agents act on. It is not part of the graph state: agents only ever ask, and every change
goes through gate.py, which checks the tool, asks a human before anything irreversible, and runs it once.

What to look at
    Desk, load_desk()      tasks, events and notes with one shared id counter, so "task 7" and "event 7" can never
                           both exist and a delete aimed at the wrong kind fails loudly. load_desk() accepts last
                           week's seed files too, and refuses a damaged file instead of guessing.
    TOOLS                  the twelve tools. Each has a risk tier set HERE in code, where no prompt can change it:
                           read (look), write (change, can be undone), irreversible (asks a human first).
    TASK_TOOLS, CALENDAR_TOOLS, TEAM_TOOLS, ALL_TOOLS
                           the allow-lists. A worker gets only its own list (least privilege), the single agent of
                           W7-0 gets all twelve.
    desk_view()            the desk as text lines, cut to PREVIEW_CHARS per item, so one huge note cannot hide the rest.
    tool_menu()            the tool menu a model reads, built from the same Tool objects that run, so it is never
                           written twice.
"""
import json
from dataclasses import dataclass, field
from typing import Any, Callable

PREVIEW_CHARS = 100     # each item is cut to this many characters in a view, so one huge note cannot hide the rest
MAX_TEXT = 200          # the longest text a tool accepts (a task, a title, a note)
DELETE_WORDS = ("delete", "remove", "clear", "cancel", "erase", "wipe")   # words that ask for something irreversible


@dataclass
class Tool:
    """A tool is a contract: what the model may ask for, how risky it is, and how to check and run it."""
    name: str
    description: str                                   # shown to the model in the menu
    params: dict[str, str]                             # parameter name -> type word, shown to the model
    risk: str                                          # "read", "write" or "irreversible"; NOT shown to the model
    validate: Callable[[dict[str, Any]], "str | None"]  # a problem sentence, or None when the input is fine
    run: Callable[[dict[str, Any], Any], str]          # (args, desk) -> short result text; raises on failure
    describe: "Callable[[dict[str, Any], Any], str] | None" = None   # plain words for the approval question


@dataclass
class Desk:
    """Everything the agents work on. It lives in the program's hands, never in a model's memory."""
    tasks: list[dict] = field(default_factory=list)    # {"id", "text", "done", "archived"}
    events: list[dict] = field(default_factory=list)   # {"id", "when", "title"}
    notes: list[dict] = field(default_factory=list)    # {"id", "text"}
    next_id: int = 1                                   # one counter for every kind of item


def new_desk() -> Desk:
    """An empty desk."""
    return Desk()


def desk_from_dict(data: Any) -> Desk:
    """Build a Desk from saved JSON. Raises ValueError on a damaged shape instead of silently guessing."""
    if not isinstance(data, dict) or not isinstance(data.get("tasks", []), list) or not isinstance(data.get("next_id"), int):
        raise ValueError("a desk file needs a 'tasks' list and an integer 'next_id'")
    desk = Desk(next_id=data["next_id"])
    seen: set[int] = set()
    for kind, keys in (("tasks", ("text",)), ("events", ("when", "title")), ("notes", ("text",))):
        for item in data.get(kind, []):
            if not isinstance(item, dict) or not _is_int(item.get("id")) or not all(isinstance(item.get(k), str) for k in keys):
                raise ValueError(f"a {kind[:-1]} in the desk file has the wrong shape: {str(item)[:80]}")
            if item["id"] in seen:
                raise ValueError(f"id {item['id']} appears twice in the desk file")
            seen.add(item["id"])
            clean = {"id": item["id"], **{k: item[k] for k in keys}}
            if kind == "tasks":
                clean.update(done=bool(item.get("done", False)), archived=bool(item.get("archived", False)))
            getattr(desk, kind).append(clean)
    if seen and desk.next_id <= max(seen):
        raise ValueError("next_id must be above every saved id")
    return desk


def load_desk(path: str) -> Desk:
    """Read a desk (or last week's task list) from a JSON file. A missing or damaged file raises."""
    with open(path, encoding="utf-8") as handle:
        try:
            data = json.load(handle)
        except json.JSONDecodeError as err:
            raise ValueError(f"{path} is not valid JSON: {err}") from None
    return desk_from_dict(data)


def desk_to_dict(desk: Desk) -> dict:
    """The desk as plain JSON-ready data (for the report and the scenario checks)."""
    return {"next_id": desk.next_id, "tasks": [dict(t) for t in desk.tasks],
            "events": [dict(e) for e in desk.events], "notes": [dict(n) for n in desk.notes]}


def _is_text(value: Any) -> bool:
    """True for a non-blank string of at most MAX_TEXT characters."""
    return isinstance(value, str) and value.strip() != "" and len(value) <= MAX_TEXT


def _is_int(value: Any) -> bool:
    """True for a real integer. Python counts True/False as ints, so they are rejected explicitly."""
    return isinstance(value, int) and not isinstance(value, bool)


def _same(text: str) -> str:
    """The duplicate rule's yardstick: lower case, trimmed, inner spaces collapsed."""
    return " ".join(text.lower().split())


def _new_id(desk: Desk) -> int:
    """Hand out the next id. One counter for tasks, events and notes."""
    desk.next_id += 1
    return desk.next_id - 1


def _find(items: list[dict], item_id: Any, kind: str) -> dict:
    """The item with this id, or a plain error. A missing id is never a fake success."""
    for item in items:
        if item["id"] == item_id:
            return item
    raise ValueError(f"no {kind} with id {item_id}")


def _need_id(args: dict) -> "str | None":
    """Input check for tools that take one integer id."""
    return None if _is_int(args.get("id")) else "id must be an integer"


def _need_text(key: str) -> Callable[[dict], "str | None"]:
    """Input check for tools that take one text field."""
    return lambda args: None if _is_text(args.get(key)) else f"{key} must be a non-empty string of at most {MAX_TEXT} characters"


# ---- the tasks ----
def _add_task(args: dict, desk: Desk) -> str:
    """Add a task unless an equal one exists. Raising turns the refusal into an error line the model can read."""
    for task in desk.tasks:
        if _same(task["text"]) == _same(args["text"]) and not task["archived"]:
            raise ValueError(f"duplicate of task {task['id']}")
    task = {"id": _new_id(desk), "text": args["text"].strip(), "done": False, "archived": False}
    desk.tasks.append(task)
    return f"added task {task['id']}"


def _list_tasks(_args: dict, desk: Desk) -> str:
    """One line per open task, cut to PREVIEW_CHARS, so every id stays visible however long one task is."""
    lines = [f"{t['id']}: {t['text'][:PREVIEW_CHARS]}{' (done)' if t['done'] else ''}" for t in desk.tasks if not t["archived"]]
    return "\n".join(lines) or "no tasks"


def _complete_task(args: dict, desk: Desk) -> str:
    """Mark a task done. It stays on the list, so this can be undone."""
    _find(desk.tasks, args["id"], "task")["done"] = True
    return f"completed task {args['id']}"


def _archive_task(args: dict, desk: Desk) -> str:
    """Hide a task from the list but keep it, so this can be undone. Not the same as delete."""
    _find(desk.tasks, args["id"], "task")["archived"] = True
    return f"archived task {args['id']}"


def _rename_task(args: dict, desk: Desk) -> str:
    """Change a task's text."""
    _find(desk.tasks, args["id"], "task")["text"] = args["text"].strip()
    return f"renamed task {args['id']}"


def _describe_delete(args: dict, desk: Desk) -> str:
    """Plain words for the approval question: the human sees the real task text, not just a number."""
    task = next((t for t in desk.tasks if t["id"] == args.get("id")), None)
    return f'delete task {task["id"]}: "{task["text"][:60]}"' if task else f"delete task {args.get('id')} (no such task)"


def _delete_task(args: dict, desk: Desk) -> str:
    """Remove a task for good. It changes nothing before it can fail."""
    desk.tasks.remove(_find(desk.tasks, args["id"], "task"))
    return f"deleted task {args['id']}"


def _describe_clear(_args: dict, desk: Desk) -> str:
    """Plain words for clearing every done task: how many, and which."""
    done = [t for t in desk.tasks if t["done"]]
    return f"delete {len(done)} done task(s): " + ", ".join(f'{t["id"]} "{t["text"][:30]}"' for t in done[:5])


def _clear_done(_args: dict, desk: Desk) -> str:
    """Delete every task marked done."""
    gone = [t["id"] for t in desk.tasks if t["done"]]
    desk.tasks = [t for t in desk.tasks if not t["done"]]
    return f"deleted {len(gone)} done task(s)"


# ---- the calendar ----
def _add_event(args: dict, desk: Desk) -> str:
    """Put an event on the calendar."""
    event = {"id": _new_id(desk), "when": args["when"].strip(), "title": args["title"].strip()}
    desk.events.append(event)
    return f"added event {event['id']}"


def _list_events(_args: dict, desk: Desk) -> str:
    """One line per event: 'id: when, title'."""
    return "\n".join(f"{e['id']}: {e['when']}, {e['title'][:PREVIEW_CHARS]}" for e in desk.events) or "no events"


def _describe_cancel(args: dict, desk: Desk) -> str:
    """Plain words for cancelling an event, so the human sees which one."""
    event = next((e for e in desk.events if e["id"] == args.get("id")), None)
    return f'cancel event {event["id"]}: "{event["when"]}, {event["title"][:50]}"' if event else f"cancel event {args.get('id')} (no such event)"


def _cancel_event(args: dict, desk: Desk) -> str:
    """Remove an event for good."""
    desk.events.remove(_find(desk.events, args["id"], "event"))
    return f"cancelled event {args['id']}"


# ---- the notes ----
def _add_note(args: dict, desk: Desk) -> str:
    """Keep a note."""
    note = {"id": _new_id(desk), "text": args["text"].strip()}
    desk.notes.append(note)
    return f"added note {note['id']}"


def _search_notes(args: dict, desk: Desk) -> str:
    """Notes containing the words asked for."""
    hits = [n for n in desk.notes if _same(args["query"]) in _same(n["text"])]
    return "\n".join(f"{n['id']}: {n['text'][:PREVIEW_CHARS]}" for n in hits) or "no matching notes"


def _both(args: dict) -> "str | None":
    """Input check for add_event: both fields must be short, non-empty text."""
    return _need_text("when")(args) or _need_text("title")(args)


TOOLS: dict[str, Tool] = {t.name: t for t in [
    Tool("add_task", "Add a new task to the to-do list.", {"text": "string"}, "write", _need_text("text"), _add_task),
    Tool("list_tasks", "List open tasks with their numeric ids.", {}, "read", lambda a: None, _list_tasks),
    Tool("complete_task", "Mark a task as done (it stays on the list).", {"id": "integer"}, "write", _need_id, _complete_task),
    Tool("archive_task", "Archive a task: hide it from the list but keep it (can be undone).", {"id": "integer"}, "write", _need_id, _archive_task),
    Tool("delete_task", "Permanently delete a task by its numeric id.", {"id": "integer"}, "irreversible", _need_id, _delete_task, _describe_delete),
    Tool("rename_task", "Change the text of a task.", {"id": "integer", "text": "string"}, "write",
         lambda a: _need_id(a) or _need_text("text")(a), _rename_task),
    Tool("clear_done", "Permanently delete every task marked done.", {}, "irreversible", lambda a: None, _clear_done, _describe_clear),
    Tool("add_event", "Add a calendar event.", {"when": "string, e.g. Fri 27 Nov 10:00", "title": "string"}, "write", _both, _add_event),
    Tool("list_events", "List calendar events with their numeric ids.", {}, "read", lambda a: None, _list_events),
    Tool("cancel_event", "Permanently cancel a calendar event by its numeric id.", {"id": "integer"}, "irreversible", _need_id, _cancel_event, _describe_cancel),
    Tool("add_note", "Save a free-text note.", {"text": "string"}, "write", _need_text("text"), _add_note),
    Tool("search_notes", "Find notes containing some words.", {"query": "string"}, "read", _need_text("query"), _search_notes),
]}

TASK_TOOLS = ["add_task", "list_tasks", "complete_task", "archive_task", "delete_task"]   # the tasks worker's allow-list
CALENDAR_TOOLS = ["add_event", "list_events", "cancel_event"]                            # the calendar worker's allow-list
TEAM_TOOLS = TASK_TOOLS + CALENDAR_TOOLS                                                 # what the planner may plan with
ALL_TOOLS = list(TOOLS)                                                                  # all twelve: the W7-0 single agent


def tool_menu(names: list[str]) -> str:
    """The tool menu a model reads, one line per tool, built from the Tool objects that actually run."""
    lines = []
    for name in names:
        tool = TOOLS[name]
        params = ", ".join(f"{k}: {v}" for k, v in tool.params.items())
        lines.append(f"- {name}({params}): {tool.description}")
    return "\n".join(lines)


def desk_view(desk: Desk, part: str = "all", preview: "int | None" = PREVIEW_CHARS) -> str:
    """The desk as text: 'tasks:' and/or 'events:' sections, one 'id: text' line per item.

    part is "all", "tasks" or "events" (a worker sees only its part). preview=None shows full text, which is what
    makes a huge note dangerous in a handoff; the handoff cap in W7-3 is what keeps that safe.
    """
    def cut(text: str) -> str:
        """Trim one item to the preview length."""
        return text if preview is None else text[:preview]

    sections = []
    if part in ("all", "tasks"):
        tasks = [f"{t['id']}: {cut(t['text'])}{' (done)' if t['done'] else ''}" for t in desk.tasks if not t["archived"]]
        sections.append("tasks:\n" + ("\n".join(tasks) or "no tasks"))
    if part in ("all", "events"):
        events = [f"{e['id']}: {e['when']}, {cut(e['title'])}" for e in desk.events]
        sections.append("events:\n" + ("\n".join(events) or "no events"))
    return "\n".join(sections)
