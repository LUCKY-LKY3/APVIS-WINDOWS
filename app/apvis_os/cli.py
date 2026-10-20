"""Bounded apvisctl interface for inspection and explicit local recovery."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from .ask import ROLES, AskConfig, AskService
from .assumptions import AssumptionLedger
from .automation import AutomationEngine
from .focus import FocusKind, FocusRecord, FocusStore
from .intelligence import DataSensitivity, DestinationPolicy, explain_route
from .memory import MemoryKind, MemoryStore
from .missions import MissionControl, summary
from . import semantic
from .vault import MemoryInbox, Vault
from .aviation import Area, AviationFeed, describe, cache_path as aviation_cache
from .nucleus import NucleusShape, clear_preview, read_preview, write_preview
from .manifests import validate_automation_manifest, validate_extension_manifest
from .projection import DisplayContext, ShellProjector
from .system_graph import SystemGraph
from .task_state import TaskStore


def _print(value: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True))
    elif isinstance(value, list):
        for item in value:
            print(item)
    else:
        print(json.dumps(value, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="apvisctl", description="APVIS OS inspection and explicit local controls")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    sub = parser.add_subparsers(dest="command", required=True)
    system = sub.add_parser("system", help="inspect local system observations")
    system.add_argument("subject", choices=["identity", "uptime", "cpu", "memory", "storage", "network", "graphics", "processes", "all"], nargs="?", default="all")
    task = sub.add_parser("task", help="inspect persisted task records")
    task_sub = task.add_subparsers(dest="task_command", required=True)
    task_sub.add_parser("list", help="list task identifiers")
    task_sub.add_parser("incomplete", help="list tasks that may need recovery")
    show = task_sub.add_parser("show", help="show a task record")
    show.add_argument("task_id")
    recover = task_sub.add_parser("recover", help="mark stale active tasks interrupted without replaying them")
    recover.add_argument("--stale-after", type=int, default=300, help="minimum task age in seconds")
    recover.add_argument("--reason", default="apvisctl recovery", help="recorded recovery reason")
    focus = sub.add_parser("focus", help="inspect or change the active contextual Focus")
    focus_sub = focus.add_subparsers(dest="focus_command", required=True)
    focus_sub.add_parser("show", help="show the active Focus and revision")
    focus_set = focus_sub.add_parser("set", help="set Focus using an expected revision")
    focus_set.add_argument("--kind", choices=[item.value for item in FocusKind], required=True)
    focus_set.add_argument("--target", required=True)
    focus_set.add_argument("--label", required=True)
    focus_set.add_argument("--workspace-id")
    focus_set.add_argument("--task-id")
    focus_set.add_argument("--sensitivity", choices=[item.value for item in DataSensitivity], default=DataSensitivity.PRIVATE.value)
    focus_set.add_argument("--expected-revision", type=int, required=True)
    focus_clear = focus_sub.add_parser("clear", help="clear Focus using an expected revision")
    focus_clear.add_argument("--expected-revision", type=int, required=True)
    surface = sub.add_parser("surface", help="inspect a privacy-aware shell state projection")
    surface.add_argument("--context", choices=[item.value for item in DisplayContext], default=DisplayContext.PRIVATE.value)
    nucleus = sub.add_parser("nucleus", help="developer preview of Nucleus shapes (always labelled, expires)")
    nucleus_sub = nucleus.add_subparsers(dest="nucleus_command", required=True)
    preview = nucleus_sub.add_parser("preview", help="show a shape for a limited time")
    preview.add_argument("--shape", choices=[item.value for item in NucleusShape], required=True)
    preview.add_argument("--lat", type=float)
    preview.add_argument("--lon", type=float)
    preview.add_argument("--label")
    preview.add_argument("--seconds", type=int, default=120)
    nucleus_sub.add_parser("clear", help="end any preview now")
    nucleus_sub.add_parser("show", help="show the active preview, if any")
    memory = sub.add_parser("memory", help="inspect explicitly stored memory")
    memory_sub = memory.add_subparsers(dest="memory_command", required=True)
    search = memory_sub.add_parser("search", help="retrieve relevant non-expired records")
    search.add_argument("query")
    search.add_argument("--kind", choices=[item.value for item in MemoryKind])
    search.add_argument("--limit", type=int, default=8)
    assumption = sub.add_parser("assumption", help="inspect or explicitly resolve task assumptions")
    assumption_sub = assumption.add_subparsers(dest="assumption_command", required=True)
    assumption_list = assumption_sub.add_parser("list", help="list assumptions for a task")
    assumption_list.add_argument("task_id")
    assumption_context = assumption_sub.add_parser("context", help="show only open assumptions for context")
    assumption_context.add_argument("task_id")
    assumption_resolve = assumption_sub.add_parser("resolve", help="confirm, reject, or supersede an assumption")
    assumption_resolve.add_argument("task_id")
    assumption_resolve.add_argument("assumption_id")
    assumption_resolve.add_argument("--status", choices=["confirmed", "rejected", "superseded"], required=True)
    assumption_resolve.add_argument("--decision")
    ask = sub.add_parser("ask", help="ask the local Ollama model a question (LOCAL ONLY)")
    ask.add_argument("question", nargs="+")
    ask.add_argument("--role", choices=ROLES, help="override automatic model choice")
    ask.add_argument("--model", help="use this installed model")
    sub.add_parser("ask-status", help="show the Ollama endpoint and which model each role would use")
    ask_config = sub.add_parser("ask-config", help="show or change Ask settings")
    ask_config.add_argument("--url", help="Ollama on this machine or the local network, e.g. http://192.168.1.20:11434")
    ask_config.add_argument("--role-model", nargs=2, action="append", metavar=("ROLE", "MODEL"),
                            help="put MODEL first for ROLE (fast, general, code)")
    mission = sub.add_parser("mission", help="Mission Control: do things, with approval before any change")
    mission_sub = mission.add_subparsers(dest="mission_command", required=True)
    mission_do = mission_sub.add_parser("do", help="plan an action from plain words (changes wait for approval)")
    mission_do.add_argument("request", nargs="+")
    mission_sub.add_parser("list", help="recent missions")
    mission_approve = mission_sub.add_parser("approve", help="approve a waiting mission")
    mission_approve.add_argument("mission_id")
    mission_approve.add_argument("token", help="approval token shown by 'mission list'")
    mission_cancel = mission_sub.add_parser("cancel", help="cancel a waiting mission")
    mission_cancel.add_argument("mission_id")
    mission_sub.add_parser("archive", help="move finished missions out of the list")
    vault = sub.add_parser("vault", help="your Markdown vault and Memory Inbox")
    vault_sub = vault.add_subparsers(dest="vault_command", required=True)
    vault_sub.add_parser("list", help="notes in the vault")
    vault_search = vault_sub.add_parser("search", help="search notes")
    vault_search.add_argument("query", nargs="+")
    vault_sub.add_parser("inbox", help="proposals waiting for review")
    vault_remember = vault_sub.add_parser("remember", help="propose a note (it waits in the inbox)")
    vault_remember.add_argument("text", nargs="+")
    vault_accept = vault_sub.add_parser("accept", help="save a proposal to the vault")
    vault_accept.add_argument("proposal_id")
    vault_reject = vault_sub.add_parser("reject", help="discard a proposal")
    vault_reject.add_argument("proposal_id")
    osiris = sub.add_parser("osiris", help="OSIRIS public feeds (aviation: ADSB.lol, ODbL)")
    osiris_sub = osiris.add_subparsers(dest="osiris_command", required=True)
    flights = osiris_sub.add_parser("flights", help="live aircraft near a point (fetches from the internet)")
    flights.add_argument("--lat", type=float, default=54.5)
    flights.add_argument("--lon", type=float, default=-3.5)
    flights.add_argument("--radius", type=int, default=250, help="nautical miles (max 250)")
    flights.add_argument("--limit", type=int, default=20)
    route = sub.add_parser("route", help="explain capability routing without invoking a provider")
    route_sub = route.add_subparsers(dest="route_command", required=True)
    explain = route_sub.add_parser("explain", help="explain a named capability alias")
    explain.add_argument("alias")
    explain.add_argument("--privacy", choices=[item.value for item in DestinationPolicy], default=DestinationPolicy.LOCAL_ONLY.value, help="hard destination policy")
    explain.add_argument("--data-sensitivity", choices=[item.value for item in DataSensitivity], default=DataSensitivity.PRIVATE.value)
    validate = sub.add_parser("validate", help="validate a manifest without installing it")
    validate.add_argument("kind", choices=["automation", "extension"])
    validate.add_argument("path", type=Path)
    automation = sub.add_parser("automation", help="run one explicitly requested automation")
    automation_sub = automation.add_subparsers(dest="automation_command", required=True)
    automation_run = automation_sub.add_parser("run", help="evaluate and run a manifest through Action Engine")
    automation_run.add_argument("path", type=Path)
    automation_run.add_argument("--trigger", default="manual")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "system":
            graph = SystemGraph()
            if args.subject == "all":
                value = [item.to_dict() for item in graph.snapshot()]
            else:
                value = getattr(graph, args.subject)().to_dict()
            _print(value, args.json)
            return 0
        if args.command == "focus":
            store = FocusStore()
            if args.focus_command == "show":
                value = store.get()
            elif args.focus_command == "clear":
                value = store.clear(expected_revision=args.expected_revision)
            else:
                record = FocusRecord(
                    uuid4().hex, FocusKind(args.kind), args.target, args.label,
                    workspace_id=args.workspace_id, task_id=args.task_id,
                    sensitivity=DataSensitivity(args.sensitivity),
                )
                value = store.set(record, expected_revision=args.expected_revision)
            _print(value.to_dict(), args.json)
            return 0
        if args.command == "nucleus":
            if args.nucleus_command == "preview":
                active = write_preview(args.shape, seconds=args.seconds, lat=args.lat, lon=args.lon, label=args.label)
            elif args.nucleus_command == "clear":
                clear_preview()
                active = None
            else:
                active = read_preview()
            value = None if active is None else {
                "shape": active.shape.value, "expires_at": active.expires_at, "pin": active.pin(), "preview": True,
            }
            _print({"preview": value}, args.json)
            return 0
        if args.command == "ask":
            question = " ".join(args.question)
            if args.json:
                result = AskService().ask(question, role=args.role, model=args.model)
            else:
                shown = [0]

                def stream(text: str) -> None:
                    print(text[shown[0]:], end="", flush=True)
                    shown[0] = len(text)

                result = AskService().ask(question, role=args.role, model=args.model, on_text=stream)
                print()
            if args.json:
                _print(result.to_dict(), True)
            elif result.status == "completed":
                print(f"-- {result.model} · local · first words {result.first_token_s}s · total {result.total_s}s", file=sys.stderr)
            else:
                print(f"Ask {result.status}: {result.error}", file=sys.stderr)
            return 0 if result.status == "completed" else 2
        if args.command == "mission":
            control = MissionControl()
            if args.mission_command == "do":
                state = control.propose(" ".join(args.request))
                if state is None:
                    raise ValueError("that is not something Mission Control can do; try apvisctl ask")
                value = summary(state)
            elif args.mission_command == "approve":
                value = summary(control.approve(args.mission_id, args.token))
            elif args.mission_command == "cancel":
                value = summary(control.cancel(args.mission_id))
            elif args.mission_command == "archive":
                value = {"archived": control.archive_finished()}
            else:
                control.expire()
                value = [summary(state) for state in control.recent()]
            _print(value, True)
            return 0 if not isinstance(value, dict) or value.get("status") != "failed" else 2
        if args.command == "vault":
            store, inbox = Vault(), MemoryInbox()
            if args.vault_command == "list":
                value = [note.summary(store.root) for note in store.notes()]
            elif args.vault_command == "search":
                value = [{"score": round(score, 2), **note.summary(store.root)} for score, note in semantic.search(store, " ".join(args.query))]
            elif args.vault_command == "inbox":
                value = [vars(p) for p in inbox.pending()]
            elif args.vault_command == "remember":
                value = vars(inbox.propose(" ".join(args.text)))
            elif args.vault_command == "accept":
                value = vars(inbox.accept(args.proposal_id))
            else:
                value = vars(inbox.reject(args.proposal_id))
            _print(value, True)
            return 0
        if args.command == "osiris":
            feed = AviationFeed(Area(args.lat, args.lon, args.radius), cache=aviation_cache())
            snapshot = feed.fetch()
            if args.json:
                _print(snapshot.to_dict(), True)
            else:
                data = snapshot.to_dict()
                print(f"{data['status'].upper()}: {data['count']} aircraft · {data['attribution']}")
                if data["error"]:
                    print(data["error"])
                for aircraft in snapshot.aircraft[: max(0, args.limit)]:
                    print("  " + describe(aircraft))
            return 0 if snapshot.status == "live" else 2
        if args.command == "ask-status":
            _print(AskService().status(), args.json)
            return 0
        if args.command == "ask-config":
            config = AskConfig.load()
            if args.url or args.role_model:
                if args.url:
                    config.ollama_url = args.url
                for role, model in args.role_model or []:
                    if role not in ROLES:
                        raise ValueError(f"unknown role {role!r}")
                    config.roles[role] = [model] + [m for m in config.roles[role] if m != model]
                config.save()
            _print({"ollama_url": config.ollama_url, "roles": config.roles, "destination_policy": config.destination_policy}, args.json)
            return 0
        if args.command == "surface":
            value = ShellProjector().snapshot(DisplayContext(args.context))
            _print(value.to_dict(), args.json)
            return 0
        if args.command == "task":
            store = TaskStore()
            if args.task_command == "list":
                value = store.list_ids()
            elif args.task_command == "incomplete":
                value = store.list_incomplete()
            elif args.task_command == "recover":
                value = store.recover_interrupted(stale_after_seconds=args.stale_after, reason=args.reason)
            else:
                value = store.load(args.task_id).to_dict()
            _print(value, args.json)
            return 0
        if args.command == "memory":
            store = MemoryStore()
            kinds = {MemoryKind(args.kind)} if args.kind else None
            value = [record.to_dict() for record in store.retrieve(args.query, kinds=kinds, limit=args.limit)]
            _print(value, args.json)
            return 0
        if args.command == "assumption":
            ledger = AssumptionLedger()
            if args.assumption_command == "list":
                value = [record.to_dict() for record in ledger.list(args.task_id)]
            elif args.assumption_command == "context":
                value = ledger.context(args.task_id)
            else:
                value = ledger.resolve(args.task_id, args.assumption_id, status=args.status, decision=args.decision).to_dict()
            _print(value, args.json)
            return 0
        if args.command == "automation":
            result = AutomationEngine().run(str(args.path), trigger_type=args.trigger)
            _print(result.to_dict(), args.json)
            return 0 if result.status in {"completed", "disabled", "not_due", "blocked"} else 2
        if args.command == "route":
            value = explain_route(args.alias, DestinationPolicy(args.privacy), DataSensitivity(args.data_sensitivity))
            _print(value, args.json)
            return 0
        validator = validate_automation_manifest if args.kind == "automation" else validate_extension_manifest
        value = validator(args.path)
        _print({"status": "valid", "kind": args.kind, "manifest": value}, args.json)
        return 0
    except (KeyError, OSError, ValueError, PermissionError, json.JSONDecodeError) as exc:
        _print({"status": "invalid" if args.command == "validate" else "unavailable", "error": str(exc)}, True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
