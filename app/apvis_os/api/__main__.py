"""python3 -m apvis_os.api [serve | page NAME | ask TEXT | query TEXT | status]

serve        run the API on its own (Home normally runs it)
page NAME    open a Home page (keyboard shortcuts use this)
ask TEXT     ask on the Home screen
query TEXT   ask from the terminal; the answer streams here
status       what would answer right now
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

from .home import home_command
from .server import HOST, PORT, serve


def _post_stream(port: int, question: str) -> int:
    request = urllib.request.Request(f"http://{HOST}:{port}/v1/ask", data=json.dumps({"question": question, "stream": True}).encode(),
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            for line in response:
                event = json.loads(line)
                if event.get("done"):
                    sys.stdout.write("\n")
                    where = {"gaming-pc": "gaming PC", "remembered": "remembered", "instant": "instant"}.get(event.get("source"), "local")
                    speed = f" · {event['tokens_per_s']:.0f} tok/s" if event.get("tokens_per_s") else ""
                    print(f"[{event.get('model') or 'APVIS'} · {where} · {event.get('total_s') or 0:.1f} s{speed}]", file=sys.stderr)
                    return 0 if not event.get("error") else 1
                sys.stdout.write(event.get("text", ""))
                sys.stdout.flush()
    except (urllib.error.URLError, OSError) as exc:
        print(f"The APVIS API isn't answering ({exc}). Is APVIS Home running?", file=sys.stderr)
        return 1
    return 1


def raise_home() -> None:
    """Bring Home in front of open apps (V4 image: the taskbar's APVIS button, Win+Space). Wayland apps
    can't raise themselves, so this asks the compositor through wlrctl; without it nothing happens."""
    wlrctl = shutil.which("wlrctl")
    if wlrctl:
        try:
            subprocess.run([wlrctl, "toplevel", "focus", "app_id:apvis-home"], timeout=3, check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m apvis_os.api", description="The APVIS API (local AI endpoint on 127.0.0.1)")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("command", nargs="?", choices=["serve", "page", "ask", "query", "status"], default="serve")
    parser.add_argument("value", nargs="*")
    args = parser.parse_args(argv)
    value = " ".join(args.value)
    if args.command in {"page", "ask"}:
        done = home_command({args.command: value}, args.port)
        if done:
            raise_home()
        return 0 if done else 1
    if args.command == "query":
        return _post_stream(args.port, value) if value else 2
    if args.command == "status":
        try:
            with urllib.request.urlopen(f"http://{HOST}:{args.port}/v1/health", timeout=10) as response:
                print(json.dumps(json.load(response), indent=2))
            return 0
        except (urllib.error.URLError, OSError) as exc:
            print(f"The APVIS API isn't answering ({exc}).", file=sys.stderr)
            return 1
    server = serve(HOST, args.port)
    print(f"APVIS API on http://{HOST}:{args.port}  (GET /v1 lists every endpoint; Ctrl+C stops it)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
