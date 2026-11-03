#!/bin/sh
# toolbox installer. Reads tools/<tool>/tool.json, links each entry onto
# PATH and each other link into place. Safe to re-run.
#
#   ./install.sh             every tool
#   ./install.sh <tool>...   just these
#   ./install.sh --list      each tool, its template, and anything it needs
#
# A real file in the way is moved aside to <path>.pre-toolbox.<time>.
# A symlink in the way is replaced. TOOLBOX_BIN changes the PATH folder.
set -eu
ROOT=$(cd "$(dirname "$0")" && pwd)
exec python3 - "$ROOT" "${TOOLBOX_BIN:-$HOME/.local/bin}" "$@" <<'PY'
import glob, json, os, shutil, sys, time

root, bindir, args = sys.argv[1], sys.argv[2], sys.argv[3:]
tools = {}
for path in sorted(glob.glob(os.path.join(root, "tools", "*", "tool.json"))):
    with open(path) as f:
        m = json.load(f)
    tools[m["name"]] = m


def link(src, dest):
    dest = os.path.expanduser(dest)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.islink(dest):
        os.remove(dest)
    elif os.path.exists(dest):
        aside = f"{dest}.pre-toolbox.{time.strftime('%Y%m%d%H%M%S')}"
        shutil.move(dest, aside)
        print(f"  moved aside  {aside}")
    os.symlink(src, dest)
    print(f"  linked       {dest.replace(os.path.expanduser('~'), '~', 1)}")


if args[:1] == ["--list"]:
    for n, m in tools.items():
        missing = [x for x in m.get("needs", []) if not shutil.which(x)]
        print(f"{n:<20} {m.get('template', ''):<26} {m['about']}")
        if missing:
            print(f"{'':<20} missing: {', '.join(missing)}")
    sys.exit(0)

unknown = [a for a in args if a not in tools]
if unknown:
    sys.exit(f"install.sh: no tool {', '.join(unknown)} (try --list)")
for n in args or tools:
    m = tools[n]
    print(n)
    for e in m.get("entries", []):
        link(os.path.join(root, e), os.path.join(bindir, os.path.basename(e)))
    for src, dest in m.get("links", {}).items():
        link(os.path.join(root, src), dest)
    missing = [x for x in m.get("needs", []) if not shutil.which(x)]
    if missing:
        print(f"  needs        {', '.join(missing)}")
PY
