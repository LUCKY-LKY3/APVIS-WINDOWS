"""Planner v1 (V3 M5): multi-step plans over APVIS's typed actions, approved once on screen.

Three ways a plan is made, safest first:
  1. Your own words, in several parts: "create a folder called Taxes in Documents and move report.pdf from
     Downloads into it". Each part goes through Mission Control's fixed parser; "it" / "there" mean the folder
     or file of the step before. No model involved.
  2. Recipes: multi-step jobs written in code ("tidy my downloads", "free up space"), built from what is
     really on disk.
  3. The local AI, only when 1 and 2 cannot: it fills a strict JSON schema of tools (Ollama structured
     output), and code checks every step (known tool, typed arguments, paths inside your home folder, apps
     that are installed). At most MAX_MODEL_STEPS steps; power actions are never allowed; a model's plan
     always waits for your approval, even if it only opens things.

Model output never runs on its own: a plan is a proposal until you approve it on the OptiPlex screen, once,
with every step listed. Then Mission Control runs the steps in order, checks each one, keeps the audit log,
and stops honestly at the first failure.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .missions import FOLDERS, ActionRequest, ParseError, Planner, find_app, is_question_like

MAX_OWNER_STEPS = 8
MAX_MODEL_STEPS = 6
RECIPE_MOVE_LIMIT = 30

_VERBS = (r"create|make|move|rename|delete|remove|trash|bin|open|launch|start|run|set|change|turn|mute|unmute|"
          r"enable|disable|check|show")
_STRONG = re.compile(r"(?i)\s*(?:,\s*)?(?:\band then\b|\bthen\b|\bafter that\b|\bafterwards\b|\bnext\b)\s*,?\s*|\s*;\s*")
_AND = re.compile(r"(?i)\s*,?\s+and\s+(?=(?:also\s+)?(?:" + _VERBS + r")\b)|\s*,\s+(?=(?:" + _VERBS + r")\b)")
_PRONOUN = re.compile(r"(?i)\b(?:into it|in it|to it|into there|in there|there|it|that folder|the folder|that file|the file)\s*([.!?]*)\s*$")


@dataclass
class Plan:
    steps: list[ActionRequest]
    source: str              # owner | recipe | model
    title: str
    note: str = ""           # shown with the plan, e.g. "the first 30 of 41 files"


def split_clauses(text: str) -> list[str]:
    """Break a request into its parts at "then", ";" and an "and" that starts a new action."""
    parts = [p for p in _STRONG.split(text.strip()) if p and p.strip()]
    out: list[str] = []
    for part in parts:
        out += [q for q in _AND.split(part) if q and q.strip()]
    return [re.sub(r"(?i)^\s*(?:and\s+)?(?:also\s+)?", "", c).strip(" ,") for c in out]


def _target(step: ActionRequest) -> str | None:
    """What "it" means after this step: the folder made, the place something moved to, the folder opened."""
    params = step.params
    if step.kind in {"create_folder", "open_folder"}:
        return params.get("path")
    if step.kind == "move":
        return params.get("dst")
    return None


def resolve_pronoun(clause: str, last: str) -> str:
    """"move report.pdf into it" -> "move report.pdf into /home/.../Taxes" (the previous step's folder)."""
    m = _PRONOUN.search(clause)
    if not m:
        return clause
    lead = re.match(r"(?i)(into|in|to)\s", m.group(0).strip())
    if lead:
        replacement = f"{lead.group(1)} {last}"
    elif clause.lower().startswith("move"):
        replacement = f"to {last}"
    else:
        replacement = last
    return clause[:m.start()].rstrip() + " " + replacement + m.group(1)


def owner_plan(planner: Planner, text: str) -> Plan | None:
    """Several actions in the owner's own words -> a plan; None if this is not a multi-part request."""
    clauses = split_clauses(text)
    if len(clauses) < 2:
        return None
    if len(clauses) > MAX_OWNER_STEPS:
        raise ParseError(f"that is more than {MAX_OWNER_STEPS} steps; ask for it in smaller parts")
    steps: list[ActionRequest] = []
    for clause in clauses:
        last = _target(steps[-1]) if steps else None
        if last:
            clause = resolve_pronoun(clause, last)
        step = planner.plan(clause)
        if step is None:
            return None                      # one part is not an action: let Ask answer the whole thing
        steps.append(step)
    return Plan(steps, "owner", f"Plan · {len(steps)} steps")


# ---------------------------------------------------------------- recipes
TYPE_FOLDERS = {
    "Images": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".heic"},
    "Documents": {".pdf", ".doc", ".docx", ".odt", ".txt", ".md", ".rtf", ".xls", ".xlsx", ".ods", ".ppt", ".pptx", ".odp", ".csv"},
    "Archives": {".zip", ".tar", ".gz", ".xz", ".7z", ".rar", ".bz2", ".zst"},
    "Installers": {".deb", ".appimage", ".exe", ".msi", ".iso", ".flatpakref", ".run"},
    "Videos": {".mp4", ".mkv", ".webm", ".mov", ".avi"},
    "Audio": {".mp3", ".flac", ".ogg", ".wav", ".m4a", ".opus"},
}
_TIDY = re.compile(r"(?i)^\s*(?:please\s+)?(?:tidy|clean|sort|organi[sz]e)\s+(?:up\s+)?(?:my\s+|the\s+)?downloads(?:\s+folder)?\s*(?:up)?\s*[.!?]*\s*$")
_FREE = re.compile(r"(?i)^\s*(?:please\s+)?(?:free\s+up|make|clear)\s+(?:some\s+)?(?:disk\s+|drive\s+)?space\s*[.!?]*\s*$")


def _kind_of(path: Path) -> str | None:
    suffix = path.suffix.lower()
    return next((folder for folder, exts in TYPE_FOLDERS.items() if suffix in exts), None)


def tidy_downloads(planner: Planner) -> Plan:
    downloads = planner.home / FOLDERS["downloads"]
    if not downloads.is_dir():
        raise ParseError("there is no Downloads folder")
    files = sorted((p for p in downloads.iterdir() if p.is_file() and not p.name.startswith(".") and _kind_of(p)),
                   key=lambda p: p.name.lower())
    if not files:
        raise ParseError("your Downloads folder is already tidy: nothing to sort into folders")
    steps, made = [], set()
    for path in files[:RECIPE_MOVE_LIMIT]:
        folder = downloads / _kind_of(path)
        if not folder.exists() and folder not in made:
            steps.append(ActionRequest("create_folder", {"path": str(folder)}, f"Create the folder {planner.show(folder)}"))
            made.add(folder)
        dst = folder / path.name
        if dst.exists():
            continue                          # never overwrite; it stays where it is
        steps.append(ActionRequest("move", {"src": str(path), "dst": str(dst)}, f"Move {path.name} to {planner.show(folder)}"))
    note = f"The first {RECIPE_MOVE_LIMIT} of {len(files)} files; ask again for the rest." if len(files) > RECIPE_MOVE_LIMIT else ""
    return Plan(steps, "recipe", "Tidy Downloads into folders by type", note)


def free_space(planner: Planner, *, now: float | None = None, min_mb: int = 100, older_days: int = 14) -> Plan:
    """Check the disk, then offer big, old downloads to the Trash (restorable), biggest first."""
    now = now or time.time()
    steps = [ActionRequest("disk_space", {}, "Check free disk space")]
    downloads = planner.home / FOLDERS["downloads"]
    big = []
    if downloads.is_dir():
        for p in downloads.iterdir():
            try:
                st = p.stat()
            except OSError:
                continue
            if p.is_file() and not p.name.startswith(".") and st.st_size >= min_mb * 1_000_000 and now - st.st_mtime > older_days * 86400:
                big.append((st.st_size, p))
    for size, p in sorted(big, reverse=True)[:5]:
        steps.append(ActionRequest("trash", {"path": str(p)}, f"Move {p.name} ({size / 1e9:.1f} GB) to Trash (you can restore it)"))
    note = "" if len(steps) > 1 else f"No downloads over {min_mb} MB older than {older_days} days were found."
    return Plan(steps, "recipe", "Free up space", note)


def recipe_plan(planner: Planner, text: str) -> Plan | None:
    if _TIDY.match(text or ""):
        return tidy_downloads(planner)
    if _FREE.match(text or ""):
        return free_space(planner)
    return None


# ---------------------------------------------------------------- the local AI writes a plan
TOOLS: dict[str, dict[str, Any]] = {
    "open_app": {"args": {"app": "string"}, "about": "open an installed app by name"},
    "open_folder": {"args": {"folder": "string"}, "about": "open a folder in Files (e.g. Documents, Downloads, Pictures/Trips)"},
    "disk_space": {"args": {}, "about": "check free disk space"},
    "system_status": {"args": {}, "about": "check CPU, memory and uptime"},
    "create_folder": {"args": {"path": "string"}, "about": "create a folder inside home (e.g. Documents/Taxes)"},
    "move": {"args": {"path": "string", "to_folder": "string"}, "about": "move a file or folder into another folder"},
    "rename": {"args": {"path": "string", "new_name": "string"}, "about": "rename a file or folder"},
    "trash": {"args": {"path": "string"}, "about": "move a file or folder to the Trash (restorable)"},
    "set_volume": {"args": {"percent": "integer"}, "about": "set the volume, 0-100"},
    "mute": {"args": {"mute": "boolean"}, "about": "mute (true) or unmute (false) the sound"},
    "wifi": {"args": {"on": "boolean"}, "about": "turn Wi-Fi on (true) or off (false)"},
}


def plan_schema() -> dict[str, Any]:
    """Ollama structured-output schema: a list of {tool, args} with only known tools."""
    return {"type": "object", "required": ["steps"], "properties": {
        "steps": {"type": "array", "maxItems": MAX_MODEL_STEPS, "items": {
            "type": "object", "required": ["tool", "args"], "properties": {
                "tool": {"type": "string", "enum": sorted(TOOLS)},
                "args": {"type": "object"}}}}}}


PLAN_PROMPT = (
    "You turn the owner's request into a short plan of computer actions. Use ONLY these tools:\n"
    + "\n".join(f"- {name}({', '.join(f'{k}: {v}' for k, v in spec['args'].items())}): {spec['about']}"
                for name, spec in TOOLS.items())
    + "\nPaths are inside the owner's home folder and always written in full from there, like Documents/Taxes "
    "or Downloads/report.pdf. Only include steps the owner asked for. "
    f"Use at most {MAX_MODEL_STEPS} steps, in order. If the request cannot be done with these tools, reply "
    "with an empty list of steps. Reply with JSON only.\n"
    'Example: "make a Taxes folder in Documents and put receipt.pdf from Downloads in it" -> '
    '{"steps": [{"tool": "create_folder", "args": {"path": "Documents/Taxes"}}, '
    '{"tool": "move", "args": {"path": "Downloads/receipt.pdf", "to_folder": "Documents/Taxes"}}]}'
)


def _str(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > 300:
        raise ParseError(f"step needs a {key.replace('_', ' ')}")
    return value.strip()


def _coerce(args: dict[str, Any]) -> dict[str, Any]:
    """Small models write 20 as "20" and true as "true": accept exactly those spellings, nothing looser."""
    out = {}
    for key, value in args.items():
        if isinstance(value, str) and re.fullmatch(r"\s*\d{1,3}\s*%?\s*", value) and key == "percent":
            value = int(value.strip().rstrip("%"))
        elif isinstance(value, str) and value.strip().lower() in {"true", "false"} and key in {"mute", "on"}:
            value = value.strip().lower() == "true"
        out[key] = value
    return out


def step_from_tool(planner: Planner, tool: str, args: Any, *, made: set[str] | None = None) -> ActionRequest:
    """One model-written step -> a typed, checked ActionRequest (or ParseError). Same rules as the owner's words."""
    if tool not in TOOLS or not isinstance(args, dict):
        raise ParseError(f"unknown tool {tool!r}")
    args = _coerce(args)
    made = made if made is not None else set()
    if tool == "open_app":
        app = _str(args, "app")
        if find_app(app, planner.app_dirs) is None:
            raise ParseError(f"no installed app called {app!r}")
        return ActionRequest("open_app", {"app": app}, f"Open {app}")
    if tool == "open_folder":
        path = planner.folder(_str(args, "folder"))
        return ActionRequest("open_folder", {"path": str(path)}, f"Open {planner.show(path)} in Files")
    if tool == "disk_space":
        return ActionRequest("disk_space", {}, "Check free disk space")
    if tool == "system_status":
        return ActionRequest("system_status", {}, "Check system status (CPU, memory, uptime)")
    if tool == "create_folder":
        path = planner.inside_home(_str(args, "path"))
        made.add(str(path))
        return ActionRequest("create_folder", {"path": str(path)}, f"Create the folder {planner.show(path)}")
    if tool == "move":
        src = planner.inside_home(_str(args, "path"))
        dst = planner.folder(_str(args, "to_folder")) / src.name
        return ActionRequest("move", {"src": str(src), "dst": str(dst)}, f"Move {planner.show(src)} to {planner.show(dst.parent)}")
    if tool == "rename":
        src = planner.inside_home(_str(args, "path"))
        new = _str(args, "new_name")
        if "/" in new or new in {".", ".."}:
            raise ParseError("a new name is just a name, not a path")
        dst = planner.inside_home(new, src.parent)
        return ActionRequest("move", {"src": str(src), "dst": str(dst)}, f"Rename {planner.show(src)} to {dst.name}")
    if tool == "trash":
        path = planner.inside_home(_str(args, "path"))
        if path == planner.home or (path.parent == planner.home and path.name in FOLDERS.values()):
            raise ParseError("APVIS will not trash your home folder or its standard folders")
        return ActionRequest("trash", {"path": str(path)}, f"Move {planner.show(path)} to Trash (you can restore it)")
    if tool == "set_volume":
        level = args.get("percent")
        if not isinstance(level, int) or isinstance(level, bool) or not 0 <= level <= 100:
            raise ParseError("volume must be between 0 and 100%")
        return ActionRequest("set_volume", {"percent": level}, f"Set the volume to {level}%")
    if tool == "mute":
        if not isinstance(args.get("mute"), bool):
            raise ParseError("mute is true or false")
        return ActionRequest("mute", {"mute": args["mute"]}, "Mute the sound" if args["mute"] else "Unmute the sound")
    if tool == "wifi":
        if not isinstance(args.get("on"), bool):
            raise ParseError("Wi-Fi is on (true) or off (false)")
        return ActionRequest("wifi", {"on": args["on"]}, f"Turn Wi-Fi {'on' if args['on'] else 'off'}")
    raise ParseError(f"unknown tool {tool!r}")


def parse_model_plan(planner: Planner, reply: str) -> list[ActionRequest]:
    """The model's JSON -> checked steps. Anything off (bad JSON, unknown tool, unsafe path, too many
    steps, a power action) rejects the whole plan: half a plan is worse than none."""
    try:
        data = json.loads(reply)
    except ValueError:
        match = re.search(r"\{.*\}", reply or "", re.S)
        if not match:
            raise ParseError("the plan was not valid JSON") from None
        try:
            data = json.loads(match.group(0))
        except ValueError:
            raise ParseError("the plan was not valid JSON") from None
    steps = data.get("steps") if isinstance(data, dict) else None
    if not isinstance(steps, list) or not steps:
        raise ParseError("there was no plan for that")
    if len(steps) > MAX_MODEL_STEPS:
        raise ParseError(f"the plan had more than {MAX_MODEL_STEPS} steps")
    made: set[str] = set()
    out = []
    for item in steps:
        if not isinstance(item, dict):
            raise ParseError("a step was not a tool call")
        step = step_from_tool(planner, str(item.get("tool", "")), item.get("args", {}), made=made)
        # The plan must hang together: whatever a step needs exists already or an earlier step makes it.
        if step.kind == "move":
            src, dst = Path(step.params["src"]), Path(step.params["dst"])
            moved_here = {d.params["dst"] for d in out if d.kind == "move"}
            if not src.exists() and str(src) not in moved_here:
                raise ParseError(f"{planner.show(src)} does not exist")
            if not dst.parent.is_dir() and str(dst.parent) not in made:
                raise ParseError(f"{planner.show(dst.parent)} does not exist and no step creates it")
        if step.kind == "trash" and not Path(step.params["path"]).exists():
            raise ParseError(f"{planner.show(Path(step.params['path']))} does not exist")
        out.append(step)
    return out


def model_plan(planner: Planner, text: str, chat: Callable[[list[dict[str, str]], dict[str, Any]], tuple[str, str]]) -> Plan:
    """Ask the local AI for a plan (chat(messages, schema) -> (reply, model)), then check it."""
    reply, model = chat([{"role": "system", "content": PLAN_PROMPT}, {"role": "user", "content": text[:800]}], plan_schema())
    steps = parse_model_plan(planner, reply)
    return Plan(steps, "model", f"Plan · {len(steps)} steps (written by {model})")


_MULTI = re.compile(r"(?i)\b(?:and|then|after that|;)\b")


def wants_model_plan(text: str) -> bool:
    """Only requests that start with an action and have more than one part go to the model; questions that
    merely start with a command word ("make a list of fruits and vegetables") are left to Ask."""
    low = (text or "").strip().lower()
    return bool(re.match(r"^(?:please\s+|can you\s+|could you\s+)?(?:" + _VERBS + r")\b", low)) and bool(_MULTI.search(low)) \
        and len(low) <= 400 and not is_question_like(low)


def propose(planner: Planner, text: str) -> Plan | None:
    """The deterministic part: a recipe or a multi-part request in the owner's words (no model)."""
    return recipe_plan(planner, text) or owner_plan(planner, text)
