
import calendar
import csv
import json
import os
import re
import shutil
import sys
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime, timedelta
from typing import Callable, Optional

TODO_FILE = "todo_list.json"
MAX_UNDO = 30
SCHEMA_VERSION = 2

PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}
PRIORITY_CHOICES = {"1": "low", "2": "medium", "3": "high"}
PRIORITY_ALIASES = {"h": "high", "m": "medium", "l": "low",
                    "high": "high", "medium": "medium", "low": "low"}
RECURRENCES = ("none", "daily", "weekly", "monthly")
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday"]

# ----------------------------------------------------------------------
# Colours
# ----------------------------------------------------------------------
if os.name == "nt":
    os.system("")  # enables ANSI escape codes on Windows 10+

USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
CODES = {"red": "31", "green": "32", "yellow": "33", "blue": "34",
         "magenta": "35", "cyan": "36", "dim": "2", "bold": "1"}


def paint(text: str, color: str) -> str:
    if not USE_COLOR:
        return text
    return f"\033[{CODES[color]}m{text}\033[0m"


# ----------------------------------------------------------------------
# Date helpers
# ----------------------------------------------------------------------
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def add_months(d: date, n: int) -> date:
    year = d.year + (d.month - 1 + n) // 12
    month = (d.month - 1 + n) % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def next_due(d: date, recurrence: str) -> date:
    if recurrence == "daily":
        return d + timedelta(days=1)
    if recurrence == "weekly":
        return d + timedelta(weeks=1)
    if recurrence == "monthly":
        return add_months(d, 1)
    return d


def parse_date(text: str) -> Optional[date]:
    """Parse a friendly date string. Returns None for empty input.
    Raises ValueError for unrecognised input."""
    t = text.strip().lower()
    if not t:
        return None
    today = date.today()

    if t in ("today", "tod"):
        return today
    if t in ("tomorrow", "tom"):
        return today + timedelta(days=1)

    m = re.fullmatch(r"\+(\d+)([dwm])", t)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if unit == "d":
            return today + timedelta(days=n)
        if unit == "w":
            return today + timedelta(weeks=n)
        return add_months(today, n)

    for i, name in enumerate(WEEKDAYS):
        if t == name or t == name[:3]:
            delta = (i - today.weekday()) % 7 or 7
            return today + timedelta(days=delta)

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date: {text!r}")


# ----------------------------------------------------------------------
# Data model
# ----------------------------------------------------------------------
@dataclass
class Task:
    id: int = 0
    title: str = "(untitled)"
    priority: str = "medium"
    completed: bool = False
    created: str = field(default_factory=now_str)
    completed_at: Optional[str] = None
    due: Optional[str] = None
    category: str = ""
    tags: list = field(default_factory=list)
    notes: str = ""
    recurrence: str = "none"
    subtasks: list = field(default_factory=list)  # [{"title": str, "done": bool}]

    @classmethod
    def from_dict(cls, raw: dict) -> "Task":
        known = {f.name for f in fields(cls)}
        data = {k: v for k, v in raw.items() if k in known}
        if data.get("priority") not in PRIORITY_RANK:
            data["priority"] = "medium"
        if data.get("recurrence") not in RECURRENCES:
            data["recurrence"] = "none"
        if not isinstance(data.get("tags"), list):
            data["tags"] = []
        if not isinstance(data.get("subtasks"), list):
            data["subtasks"] = []
        if not isinstance(data.get("id"), int):
            data["id"] = 0
        task = cls(**data)
        if task.due:
            try:
                datetime.strptime(task.due, "%Y-%m-%d")
            except ValueError:
                task.due = None
        return task

    @property
    def due_date(self) -> Optional[date]:
        return datetime.strptime(self.due, "%Y-%m-%d").date() if self.due else None

    @property
    def is_overdue(self) -> bool:
        d = self.due_date
        return bool(d and not self.completed and d < date.today())

    @property
    def subtask_progress(self) -> tuple[int, int]:
        done = sum(1 for s in self.subtasks if s.get("done"))
        return done, len(self.subtasks)


# ----------------------------------------------------------------------
# Storage + undo/redo
# ----------------------------------------------------------------------
class TodoStore:
    def __init__(self, path: str):
        self.path = path
        self.tasks: list[Task] = []
        self.archive: list[Task] = []
        self.next_id = 1
        self.undo_stack: list[tuple[str, str]] = []
        self.redo_stack: list[tuple[str, str]] = []
        self.load()

    # ---- serialisation ------------------------------------------------
    def _state(self) -> dict:
        return {
            "version": SCHEMA_VERSION,
            "next_id": self.next_id,
            "tasks": [asdict(t) for t in self.tasks],
            "archive": [asdict(t) for t in self.archive],
        }

    def _apply_state(self, data) -> None:
        # Old format was a plain list of tasks.
        if isinstance(data, list):
            data = {"tasks": data}
        if not isinstance(data, dict):
            raise ValueError("Unrecognised file format")

        self.tasks = [Task.from_dict(r) for r in data.get("tasks", [])
                      if isinstance(r, dict)]
        self.archive = [Task.from_dict(r) for r in data.get("archive", [])
                        if isinstance(r, dict)]

        used: set[int] = set()
        stored_next = data.get("next_id") if isinstance(data.get("next_id"), int) else 1
        highest = max([t.id for t in self.tasks + self.archive] + [stored_next - 1, 0])
        self.next_id = highest + 1
        for t in self.tasks + self.archive:
            if t.id <= 0 or t.id in used:
                t.id = self.next_id
                self.next_id += 1
            used.add(t.id)

    def load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self._apply_state(json.load(f))
            shutil.copy2(self.path, self.path + ".bak")
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            corrupt = self.path + ".corrupt"
            try:
                shutil.copy2(self.path, corrupt)
            except OSError:
                pass
            print(paint(f"Could not read {self.path} ({exc}). "
                        f"A copy was kept as {corrupt}. Starting fresh.", "red"))
            self.tasks, self.archive, self.next_id = [], [], 1

    def save(self) -> None:
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._state(), f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError as exc:
            print(paint(f"Could not save: {exc}", "red"))

    # ---- undo / redo --------------------------------------------------
    def checkpoint(self, label: str) -> None:
        self.undo_stack.append((label, json.dumps(self._state())))
        if len(self.undo_stack) > MAX_UNDO:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self) -> Optional[str]:
        if not self.undo_stack:
            return None
        label, snap = self.undo_stack.pop()
        self.redo_stack.append((label, json.dumps(self._state())))
        self._apply_state(json.loads(snap))
        self.save()
        return label

    def redo(self) -> Optional[str]:
        if not self.redo_stack:
            return None
        label, snap = self.redo_stack.pop()
        self.undo_stack.append((label, json.dumps(self._state())))
        self._apply_state(json.loads(snap))
        self.save()
        return label

    # ---- task operations ----------------------------------------------
    def new_task(self, **kwargs) -> Task:
        task = Task(id=self.next_id, **kwargs)
        self.next_id += 1
        self.tasks.append(task)
        return task

    def get(self, task_id: int, include_archive: bool = False) -> Optional[Task]:
        pool = self.tasks + (self.archive if include_archive else [])
        return next((t for t in pool if t.id == task_id), None)

    def complete(self, task: Task) -> Optional[Task]:
        """Mark done. If recurring, spawn the next occurrence and return it."""
        task.completed = True
        task.completed_at = now_str()
        if task.recurrence == "none":
            return None
        base = task.due_date or date.today()
        nxt = next_due(base, task.recurrence)
        while nxt < date.today():
            nxt = next_due(nxt, task.recurrence)
        return self.new_task(
            title=task.title, priority=task.priority, due=nxt.isoformat(),
            category=task.category, tags=list(task.tags), notes=task.notes,
            recurrence=task.recurrence,
            subtasks=[{"title": s["title"], "done": False} for s in task.subtasks],
        )


# ----------------------------------------------------------------------
# Input helpers
# ----------------------------------------------------------------------
def ask(prompt: str, default: str = "") -> str:
    value = input(prompt).strip()
    return value or default


def confirm(prompt: str) -> bool:
    return ask(f"{prompt} (y/n): ").lower() in ("y", "yes")


def ask_date(prompt: str, allow_clear: bool = False) -> tuple[bool, Optional[date]]:
    """Returns (changed, date). Blank input => (False, None) i.e. 'no change'.
    If allow_clear and the user types 'none' => (True, None)."""
    while True:
        raw = input(prompt).strip()
        if not raw:
            return False, None
        if allow_clear and raw.lower() in ("none", "clear", "-"):
            return True, None
        try:
            return True, parse_date(raw)
        except ValueError:
            print(paint("  Try: today, tomorrow, +3d, +2w, +1m, fri, 2026-12-31", "yellow"))


def ask_priority(prompt: str) -> Optional[str]:
    print("  1. Low   2. Medium   3. High")
    choice = input(prompt).strip().lower()
    return PRIORITY_CHOICES.get(choice) or PRIORITY_ALIASES.get(choice)


def ask_recurrence(prompt: str) -> Optional[str]:
    print("  1. None  2. Daily  3. Weekly  4. Monthly")
    choice = input(prompt).strip().lower()
    mapping = {"1": "none", "2": "daily", "3": "weekly", "4": "monthly"}
    result = mapping.get(choice) or (choice if choice in RECURRENCES else None)
    return result


def parse_tags(text: str) -> list[str]:
    seen, tags = set(), []
    for raw in re.split(r"[,\s]+", text):
        tag = raw.strip().lstrip("#").lower()
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def parse_ids(text: str) -> list[int]:
    """Parse '1,3,5-7' into [1,3,5,6,7]."""
    ids: list[int] = []
    for part in re.split(r"[,\s]+", text.strip()):
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            if a.isdigit() and b.isdigit():
                ids.extend(range(int(a), int(b) + 1))
                continue
            raise ValueError(part)
        if not part.isdigit():
            raise ValueError(part)
        ids.append(int(part))
    return list(dict.fromkeys(ids))


def pick_task(store: TodoStore, prompt: str = "Task ID: ") -> Optional[Task]:
    raw = ask(prompt)
    if not raw.isdigit():
        print(paint("Please enter a valid task ID.", "yellow"))
        return None
    task = store.get(int(raw))
    if not task:
        print(paint(f"No task with ID {raw}.", "yellow"))
    return task


def pick_tasks(store: TodoStore, prompt: str) -> list[Task]:
    raw = ask(prompt)
    if not raw:
        return []
    try:
        ids = parse_ids(raw)
    except ValueError:
        print(paint("Use IDs like: 3   or   1,4,6   or   2-5", "yellow"))
        return []
    found = []
    for i in ids:
        t = store.get(i)
        if t:
            found.append(t)
        else:
            print(paint(f"  (skipping unknown ID {i})", "dim"))
    return found


# ----------------------------------------------------------------------
# Display
# ----------------------------------------------------------------------
def truncate(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def due_label(task: Task) -> str:
    d = task.due_date
    if not d:
        return ""
    delta = (d - date.today()).days
    if task.completed:
        return paint(f"due {d.isoformat()}", "dim")
    if delta < 0:
        return paint(f"due {d.isoformat()} (overdue {-delta}d)", "red")
    if delta == 0:
        return paint(f"due {d.isoformat()} (today)", "yellow")
    if delta == 1:
        return paint(f"due {d.isoformat()} (tomorrow)", "cyan")
    if delta <= 7:
        return f"due {d.isoformat()} (in {delta}d)"
    return f"due {d.isoformat()}"


def format_task(task: Task) -> str:
    box = paint("[✓]", "green") if task.completed else "[ ]"
    prio_text = {"high": "!!!", "medium": "!! ", "low": "!  "}[task.priority]
    prio_color = {"high": "red", "medium": "yellow", "low": "green"}[task.priority]
    prio = paint(prio_text, prio_color)

    title = truncate(task.title, 36).ljust(36)
    if task.completed:
        title = paint(title, "dim")

    extras = []
    if task.due:
        extras.append(due_label(task))
    if task.category:
        extras.append(paint(f"~{task.category}", "magenta"))
    if task.tags:
        extras.append(paint(" ".join(f"#{t}" for t in task.tags), "blue"))
    if task.recurrence != "none":
        extras.append(paint(f"⟳ {task.recurrence}", "cyan"))
    done, total = task.subtask_progress
    if total:
        extras.append(f"({done}/{total} subtasks)")
    if task.notes:
        extras.append("✎")

    return f"{task.id:>4} {box} {prio} {title}  " + "  ".join(extras)


def print_tasks(tasks: list[Task], title: str = "TO-DO LIST") -> None:
    if not tasks:
        print(paint("\nNo tasks to show.", "dim"))
        return
    bar = "=" * 12
    print(f"\n{bar} {paint(title, 'bold')} ({len(tasks)}) {bar}")
    for t in tasks:
        print(format_task(t))
    print("=" * (26 + len(title)))


def sort_tasks(tasks: list[Task], mode: str) -> list[Task]:
    far = date.max
    keys: dict[str, Callable[[Task], tuple]] = {
        "due": lambda t: (t.completed, t.due_date or far, PRIORITY_RANK[t.priority], t.id),
        "priority": lambda t: (t.completed, PRIORITY_RANK[t.priority], t.due_date or far, t.id),
        "created": lambda t: (t.completed, t.created, t.id),
        "title": lambda t: (t.completed, t.title.lower(), t.id),
    }
    return sorted(tasks, key=keys.get(mode, keys["due"]))


def show_details(task: Task) -> None:
    print("\n" + "-" * 50)
    print(f"{paint(f'#{task.id}  {task.title}', 'bold')}")
    print("-" * 50)
    print(f"Status     : {'Completed ' + (task.completed_at or '') if task.completed else ('Overdue' if task.is_overdue else 'Pending')}")
    print(f"Priority   : {task.priority.upper()}")
    print(f"Created    : {task.created}")
    print(f"Due        : {due_label(task) or '—'}")
    print(f"Category   : {task.category or '—'}")
    print(f"Tags       : {' '.join('#' + t for t in task.tags) or '—'}")
    print(f"Repeats    : {task.recurrence}")
    print(f"Notes      : {task.notes or '—'}")
    if task.subtasks:
        done, total = task.subtask_progress
        print(f"Subtasks   : {done}/{total}")
        for i, s in enumerate(task.subtasks, 1):
            print(f"   {i}. [{'✓' if s['done'] else ' '}] {s['title']}")
    print("-" * 50)


# ----------------------------------------------------------------------
# Quick-add parsing
# ----------------------------------------------------------------------
def parse_quick(text: str) -> dict:
    """'Buy milk !high #home ~errands @tomorrow %weekly' -> task fields."""
    words, tags = [], []
    priority, due, category, recurrence = "medium", None, "", "none"
    for w in text.split():
        low = w.lower()
        if low.startswith("!") and low[1:] in PRIORITY_ALIASES:
            priority = PRIORITY_ALIASES[low[1:]]
        elif w.startswith("#") and len(w) > 1:
            tags.append(low[1:])
        elif w.startswith("~") and len(w) > 1:
            category = w[1:]
        elif low.startswith("%") and low[1:] in RECURRENCES:
            recurrence = low[1:]
        elif w.startswith("@") and len(w) > 1:
            try:
                due = parse_date(w[1:])
            except ValueError:
                words.append(w)
        else:
            words.append(w)
    if recurrence != "none" and not due:
        due = date.today()
    return {
        "title": " ".join(words),
        "priority": priority,
        "due": due.isoformat() if due else None,
        "category": category,
        "tags": list(dict.fromkeys(tags)),
        "recurrence": recurrence,
    }


# ----------------------------------------------------------------------
# Actions
# ----------------------------------------------------------------------
def action_add(store: TodoStore) -> None:
    print("\n---------- ADD TASK ----------")
    title = ask("Title: ")
    if not title:
        print(paint("Task cannot be empty!", "yellow"))
        return

    priority = ask_priority("Priority (1-3, Enter = medium): ") or "medium"
    _, due = ask_date("Due date (Enter to skip): ")
    category = ask("Category (Enter to skip): ")
    tags = parse_tags(ask("Tags, comma/space separated (Enter to skip): "))
    notes = ask("Notes (Enter to skip): ")
    recurrence = "none"
    if due:
        recurrence = ask_recurrence("Repeat (1-4, Enter = none): ") or "none"

    store.checkpoint(f"add '{title}'")
    task = store.new_task(title=title, priority=priority,
                          due=due.isoformat() if due else None,
                          category=category, tags=tags, notes=notes,
                          recurrence=recurrence)
    store.save()
    print(paint(f"✓ Added task #{task.id}", "green"))


def action_quick_add(store: TodoStore, text: str = "") -> None:
    if not text:
        print("\nQuick add syntax:  title !high #tag ~category @tomorrow %weekly")
        text = ask("> ")
    fields_ = parse_quick(text)
    if not fields_["title"]:
        print(paint("Task cannot be empty!", "yellow"))
        return
    store.checkpoint(f"quick add '{fields_['title']}'")
    task = store.new_task(**fields_)
    store.save()
    print(paint(f"✓ Added task #{task.id}", "green"))
    print(format_task(task))


def action_view(store: TodoStore) -> None:
    print("\nView:")
    print(" 1. All            2. Pending        3. Completed")
    print(" 4. Overdue        5. Due today      6. Next 7 days")
    print(" 7. By category    8. By tag         9. By priority")
    choice = ask("Choose (Enter = pending): ", "2")
    today = date.today()
    tasks, title = store.tasks, "ALL TASKS"

    if choice == "1":
        pass
    elif choice == "2":
        tasks, title = [t for t in store.tasks if not t.completed], "PENDING"
    elif choice == "3":
        tasks, title = [t for t in store.tasks if t.completed], "COMPLETED"
    elif choice == "4":
        tasks, title = [t for t in store.tasks if t.is_overdue], "OVERDUE"
    elif choice == "5":
        tasks = [t for t in store.tasks if not t.completed and t.due_date == today]
        title = "DUE TODAY"
    elif choice == "6":
        end = today + timedelta(days=7)
        tasks = [t for t in store.tasks
                 if not t.completed and t.due_date and today <= t.due_date <= end]
        title = "NEXT 7 DAYS"
    elif choice == "7":
        cats = sorted({t.category for t in store.tasks if t.category}, key=str.lower)
        if not cats:
            print(paint("No categories yet.", "dim"))
            return
        print("Categories: " + ", ".join(cats))
        cat = ask("Category: ").lower()
        tasks = [t for t in store.tasks if t.category.lower() == cat]
        title = f"CATEGORY: {cat}"
    elif choice == "8":
        all_tags = sorted({tag for t in store.tasks for tag in t.tags})
        if not all_tags:
            print(paint("No tags yet.", "dim"))
            return
        print("Tags: " + ", ".join(f"#{x}" for x in all_tags))
        tag = ask("Tag: ").lstrip("#").lower()
        tasks = [t for t in store.tasks if tag in t.tags]
        title = f"TAG: #{tag}"
    elif choice == "9":
        prio = ask_priority("Priority: ")
        if not prio:
            print(paint("Invalid priority.", "yellow"))
            return
        tasks = [t for t in store.tasks if t.priority == prio]
        title = f"PRIORITY: {prio.upper()}"
    else:
        print(paint("Invalid choice.", "yellow"))
        return

    sort_mode = ask("Sort by [due/priority/created/title] (Enter = due): ", "due").lower()
    print_tasks(sort_tasks(tasks, sort_mode), title)


def action_details(store: TodoStore) -> None:
    task = pick_task(store)
    if task:
        show_details(task)


def action_complete(store: TodoStore) -> None:
    pending = [t for t in store.tasks if not t.completed]
    if not pending:
        print(paint("\nNo pending tasks.", "dim"))
        return
    print_tasks(sort_tasks(pending, "due"), "PENDING")
    chosen = pick_tasks(store, "\nID(s) to complete (e.g. 3 or 1,4 or 2-5): ")
    chosen = [t for t in chosen if not t.completed]
    if not chosen:
        return

    for t in chosen:
        done, total = t.subtask_progress
        if total and done < total:
            if not confirm(f"'{t.title}' has {total - done} unfinished subtask(s). Complete anyway?"):
                chosen.remove(t)

    if not chosen:
        return
    store.checkpoint(f"complete {len(chosen)} task(s)")
    for t in chosen:
        spawned = store.complete(t)
        print(paint(f"✓ Completed: {t.title}", "green"))
        if spawned:
            print(f"  ⟳ Next occurrence created: #{spawned.id} due {spawned.due}")
    store.save()


def action_reopen(store: TodoStore) -> None:
    done = [t for t in store.tasks if t.completed]
    if not done:
        print(paint("\nNo completed tasks.", "dim"))
        return
    print_tasks(done, "COMPLETED")
    chosen = [t for t in pick_tasks(store, "\nID(s) to reopen: ") if t.completed]
    if not chosen:
        return
    store.checkpoint(f"reopen {len(chosen)} task(s)")
    for t in chosen:
        t.completed = False
        t.completed_at = None
        print(f"↩ Reopened: {t.title}")
    store.save()


def action_edit(store: TodoStore) -> None:
    task = pick_task(store, "ID of task to edit: ")
    if not task:
        return
    show_details(task)
    print("Press Enter to keep the current value.\n")

    new_title = ask("New title: ")
    new_prio = ask_priority("New priority (1-3): ")
    changed, new_due = ask_date("New due date (type 'none' to clear): ", allow_clear=True)
    new_cat = input("New category ('none' to clear): ").strip()
    new_tags = input("New tags ('none' to clear): ").strip()
    new_notes = input("New notes ('none' to clear): ").strip()
    new_rec = ask_recurrence("Repeat (1-4): ")

    store.checkpoint(f"edit #{task.id}")
    if new_title:
        task.title = new_title
    if new_prio:
        task.priority = new_prio
    if changed:
        task.due = new_due.isoformat() if new_due else None
    if new_cat:
        task.category = "" if new_cat.lower() == "none" else new_cat
    if new_tags:
        task.tags = [] if new_tags.lower() == "none" else parse_tags(new_tags)
    if new_notes:
        task.notes = "" if new_notes.lower() == "none" else new_notes
    if new_rec:
        task.recurrence = new_rec
        if new_rec != "none" and not task.due:
            task.due = date.today().isoformat()
    store.save()
    print(paint("✓ Task updated.", "green"))


def action_delete(store: TodoStore) -> None:
    if not store.tasks:
        print(paint("\nNo tasks to delete.", "dim"))
        return
    print_tasks(sort_tasks(store.tasks, "due"), "ALL TASKS")
    chosen = pick_tasks(store, "\nID(s) to delete: ")
    if not chosen:
        return
    if not confirm(f"Delete {len(chosen)} task(s)? (you can undo)"):
        print("Cancelled.")
        return
    store.checkpoint(f"delete {len(chosen)} task(s)")
    ids = {t.id for t in chosen}
    store.tasks = [t for t in store.tasks if t.id not in ids]
    store.save()
    print(paint(f"✓ Deleted {len(chosen)} task(s).", "green"))


def action_subtasks(store: TodoStore) -> None:
    task = pick_task(store, "ID of parent task: ")
    if not task:
        return
    while True:
        print(f"\nSubtasks of #{task.id} '{task.title}':")
        if not task.subtasks:
            print(paint("  (none)", "dim"))
        for i, s in enumerate(task.subtasks, 1):
            print(f"  {i}. [{'✓' if s['done'] else ' '}] {s['title']}")
        print("\n  a) add   t) toggle done   r) remove   q) back")
        choice = ask("> ").lower()

        if choice == "a":
            text = ask("Subtask: ")
            if text:
                store.checkpoint(f"add subtask to #{task.id}")
                task.subtasks.append({"title": text, "done": False})
                store.save()
        elif choice in ("t", "r") and task.subtasks:
            n = ask("Subtask number: ")
            if n.isdigit() and 1 <= int(n) <= len(task.subtasks):
                idx = int(n) - 1
                store.checkpoint(f"subtask change on #{task.id}")
                if choice == "t":
                    task.subtasks[idx]["done"] = not task.subtasks[idx]["done"]
                else:
                    task.subtasks.pop(idx)
                store.save()
            else:
                print(paint("Invalid number.", "yellow"))
        elif choice == "q":
            return


def action_search(store: TodoStore) -> None:
    kw = ask("\nSearch keyword (use #tag to search tags): ").lower()
    if not kw:
        print(paint("Search keyword cannot be empty.", "yellow"))
        return

    def matches(t: Task) -> bool:
        if kw.startswith("#"):
            return kw[1:] in t.tags
        haystack = " ".join([t.title, t.notes, t.category, " ".join(t.tags),
                             " ".join(s["title"] for s in t.subtasks)]).lower()
        return kw in haystack

    results = [t for t in store.tasks if matches(t)]
    print_tasks(sort_tasks(results, "due"), f"SEARCH: {kw}")
    if not results:
        archived = [t for t in store.archive if matches(t)]
        if archived:
            print(paint(f"({len(archived)} match(es) in the archive)", "dim"))


def bar(count: int, maximum: int, width: int = 20) -> str:
    filled = round(width * count / maximum) if maximum else 0
    return "█" * filled + "░" * (width - filled)


def action_stats(store: TodoStore) -> None:
    tasks = store.tasks
    total = len(tasks)
    done = sum(1 for t in tasks if t.completed)
    pending = total - done
    overdue = sum(1 for t in tasks if t.is_overdue)
    today = date.today()
    due_today = sum(1 for t in tasks if not t.completed and t.due_date == today)

    print("\n" + "=" * 14 + " STATISTICS " + "=" * 14)
    print(f"Total tasks      : {total}")
    print(f"Completed        : {done}")
    print(f"Pending          : {pending}")
    print(f"Overdue          : {paint(str(overdue), 'red') if overdue else 0}")
    print(f"Due today        : {due_today}")
    print(f"Archived         : {len(store.archive)}")
    if total:
        rate = done / total * 100
        print(f"Completion rate  : {bar(done, total)} {rate:.1f}%")

    if pending:
        print("\nPending by priority:")
        counts = {p: sum(1 for t in tasks if not t.completed and t.priority == p)
                  for p in ("high", "medium", "low")}
        mx = max(counts.values())
        for p, n in counts.items():
            print(f"  {p:<7}{bar(n, mx)} {n}")

        cats: dict[str, int] = {}
        for t in tasks:
            if not t.completed:
                cats[t.category or "(none)"] = cats.get(t.category or "(none)", 0) + 1
        if len(cats) > 1 or "(none)" not in cats:
            print("\nPending by category:")
            mx = max(cats.values())
            for name, n in sorted(cats.items(), key=lambda kv: -kv[1])[:8]:
                print(f"  {truncate(name, 12):<13}{bar(n, mx)} {n}")

    # Completions per day over the last 7 days (tasks + archive)
    per_day: dict[date, int] = {today - timedelta(days=i): 0 for i in range(6, -1, -1)}
    for t in store.tasks + store.archive:
        if t.completed_at:
            try:
                d = datetime.strptime(t.completed_at, "%Y-%m-%d %H:%M").date()
            except ValueError:
                continue
            if d in per_day:
                per_day[d] += 1
    if any(per_day.values()):
        print("\nCompleted in the last 7 days:")
        mx = max(per_day.values())
        for d, n in per_day.items():
            print(f"  {d.strftime('%a %d')}  {bar(n, mx, 15)} {n}")
    print("=" * 41)


def action_archive_done(store: TodoStore) -> None:
    done = [t for t in store.tasks if t.completed]
    if not done:
        print(paint("\nThere are no completed tasks to archive.", "dim"))
        return
    if not confirm(f"\nMove {len(done)} completed task(s) to the archive?"):
        print("Cancelled.")
        return
    store.checkpoint(f"archive {len(done)} task(s)")
    store.archive.extend(done)
    store.tasks = [t for t in store.tasks if not t.completed]
    store.save()
    print(paint(f"✓ Archived {len(done)} task(s).", "green"))


def action_archive_browser(store: TodoStore) -> None:
    if not store.archive:
        print(paint("\nThe archive is empty.", "dim"))
        return
    print_tasks(store.archive, "ARCHIVE")
    print("\n  r) restore   p) purge (delete forever)   q) back")
    choice = ask("> ").lower()
    if choice not in ("r", "p"):
        return
    raw = ask("ID(s): ")
    try:
        ids = set(parse_ids(raw))
    except ValueError:
        print(paint("Use IDs like: 3  or  1,4  or  2-5", "yellow"))
        return
    selected = [t for t in store.archive if t.id in ids]
    if not selected:
        print(paint("No matching archived tasks.", "yellow"))
        return
    if choice == "r":
        store.checkpoint(f"restore {len(selected)} task(s)")
        store.archive = [t for t in store.archive if t.id not in ids]
        for t in selected:
            t.completed = False
            t.completed_at = None
            store.tasks.append(t)
        print(paint(f"✓ Restored {len(selected)} task(s).", "green"))
    else:
        if not confirm(f"Permanently delete {len(selected)} archived task(s)?"):
            print("Cancelled.")
            return
        store.checkpoint(f"purge {len(selected)} task(s)")
        store.archive = [t for t in store.archive if t.id not in ids]
        print(paint(f"✓ Purged {len(selected)} task(s).", "green"))
    store.save()


def action_export_csv(store: TodoStore) -> None:
    default = f"todo_export_{datetime.now():%Y%m%d}.csv"
    path = ask(f"\nCSV file name (Enter = {default}): ", default)
    try:
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "title", "status", "priority", "due", "category",
                             "tags", "recurrence", "created", "completed_at",
                             "subtasks_done", "subtasks_total", "notes"])
            for t in store.tasks + store.archive:
                done, total = t.subtask_progress
                writer.writerow([
                    t.id, t.title, "done" if t.completed else "pending", t.priority,
                    t.due or "", t.category, ";".join(t.tags), t.recurrence,
                    t.created, t.completed_at or "", done, total, t.notes,
                ])
        print(paint(f"✓ Exported {len(store.tasks) + len(store.archive)} task(s) to {path}", "green"))
    except OSError as exc:
        print(paint(f"Export failed: {exc}", "red"))


def action_backup_import(store: TodoStore) -> None:
    print("\n  b) create backup file   i) import from backup file   q) back")
    choice = ask("> ").lower()
    if choice == "b":
        default = f"todo_backup_{datetime.now():%Y%m%d_%H%M%S}.json"
        path = ask(f"Backup file name (Enter = {default}): ", default)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(store._state(), f, indent=2, ensure_ascii=False)
            print(paint(f"✓ Backup written to {path}", "green"))
        except OSError as exc:
            print(paint(f"Backup failed: {exc}", "red"))
    elif choice == "i":
        path = ask("File to import: ")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw_list = data if isinstance(data, list) else data.get("tasks", [])
            existing = {(t.title, t.created) for t in store.tasks + store.archive}
            imported = 0
            store.checkpoint("import tasks")
            for raw in raw_list:
                if not isinstance(raw, dict):
                    continue
                t = Task.from_dict(raw)
                if (t.title, t.created) in existing:
                    continue
                t.id = store.next_id
                store.next_id += 1
                store.tasks.append(t)
                imported += 1
            store.save()
            print(paint(f"✓ Imported {imported} new task(s) (duplicates skipped).", "green"))
        except (OSError, json.JSONDecodeError, AttributeError) as exc:
            print(paint(f"Import failed: {exc}", "red"))


def action_undo(store: TodoStore) -> None:
    label = store.undo()
    print(paint(f"↩ Undid: {label}", "cyan") if label else "Nothing to undo.")


def action_redo(store: TodoStore) -> None:
    label = store.redo()
    print(paint(f"↪ Redid: {label}", "cyan") if label else "Nothing to redo.")


# ----------------------------------------------------------------------
# Menu
# ----------------------------------------------------------------------
MENU = [
    ("1", "Add task", action_add),
    ("2", "Quick add", action_quick_add),
    ("3", "View tasks (filter / sort)", action_view),
    ("4", "Task details", action_details),
    ("5", "Complete task(s)", action_complete),
    ("6", "Reopen task(s)", action_reopen),
    ("7", "Edit task", action_edit),
    ("8", "Delete task(s)", action_delete),
    ("9", "Subtasks", action_subtasks),
    ("10", "Search", action_search),
    ("11", "Statistics", action_stats),
    ("12", "Archive completed tasks", action_archive_done),
    ("13", "Browse / restore archive", action_archive_browser),
    ("14", "Export to CSV", action_export_csv),
    ("15", "Backup / import", action_backup_import),
    ("16", "Undo", action_undo),
    ("17", "Redo", action_redo),
    ("0", "Exit", None),
]


def print_menu() -> None:
    width = 38
    print("\n╔" + "═" * width + "╗")
    print("║" + "TO-DO LIST APP".center(width) + "║")
    print("╠" + "═" * width + "╣")
    for key, label, _ in MENU:
        print("║ " + f"{key:>2}. {label}".ljust(width - 1) + "║")
    print("╚" + "═" * width + "╝")


def startup_summary(store: TodoStore) -> None:
    today = date.today()
    overdue = sum(1 for t in store.tasks if t.is_overdue)
    due_today = sum(1 for t in store.tasks if not t.completed and t.due_date == today)
    pending = sum(1 for t in store.tasks if not t.completed)
    print(f"You have {pending} pending task(s).")
    if overdue:
        print(paint(f"⚠  {overdue} overdue", "red"))
    if due_today:
        print(paint(f"⏰ {due_today} due today", "yellow"))


def main() -> None:
    store = TodoStore(TODO_FILE)

    # --- command-line shortcuts ---
    args = sys.argv[1:]
    if args:
        cmd = args[0].lower()
        if cmd == "add" and len(args) > 1:
            action_quick_add(store, " ".join(args[1:]))
        elif cmd == "list":
            pending = [t for t in store.tasks if not t.completed]
            print_tasks(sort_tasks(pending, "due"), "PENDING")
        else:
            print(__doc__)
        return

    print(paint("Welcome to the To-Do List App!", "bold"))
    startup_summary(store)

    handlers = {key: fn for key, _, fn in MENU}
    try:
        while True:
            print_menu()
            choice = ask("\nEnter your choice: ")
            if choice == "0":
                store.save()
                print("\nGoodbye! 👋")
                break
            handler = handlers.get(choice)
            if handler:
                handler(store)
            else:
                print(paint("\nInvalid choice. Please pick a number from the menu.", "yellow"))
    except (KeyboardInterrupt, EOFError):
        store.save()
        print("\n\nSaved. Goodbye! 👋")


if __name__ == "__main__":
    main()
