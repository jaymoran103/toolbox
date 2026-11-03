"""Command-line entry point.

    tt <tool> [options]      one run, e.g. tt metronome 96 --for 4m
    tt run <target>          a preset, a .tt file, '-' for stdin, or inline text
    tt presets [name]        list presets, or show one
    tt help [tool]
    tt                       the menu

Installed as timer, metronome and so on, the command name picks the tool.
"""

import json
import os
import sys

from timetools import __version__, runner, spec, views

RUN_FLAGS = {"--out": "out", "--emit": "emit", "--on": "on", "--from": "start", "--view": "view"}


def split_run_flags(args, allowed):
    """Pull run-level flags out of argv. They never reach a step line."""
    found, rest, i = {"on": []}, [], 0
    while i < len(args):
        name, eq, value = args[i].partition("=")
        if name in allowed:
            if not eq:
                if i + 1 >= len(args):
                    raise spec.ParseError("%s needs a value" % name)
                value = args[i + 1]
                i += 1
            key = RUN_FLAGS[name]
            if key == "on":
                found["on"].append(value)
            else:
                found[key] = value
        else:
            rest.append(args[i])
        i += 1
    return found, rest


def finish(results, block, flags, quit):
    card = runner.score(results, block["score"]) if block and block["score"] else None
    if card:
        print(runner.scorecard_text(card))
    if flags.get("out"):
        with open(flags["out"], "w") as f:
            json.dump({"preset": block["name"] if block else None, "results": results, "score": card}, f, indent=2)
    return card


def run_tool(argv, prog):
    flags, rest = split_run_flags(argv, ("--out", "--emit", "--on"))
    if any(a in ("-h", "--help") for a in rest):
        print(spec.help_text(spec.ALIASES.get(rest[0], rest[0]), prog))
        return 0
    step = spec.parse_step(rest)
    hooks = runner.Hooks(flags.get("emit"), flags["on"])
    result = runner.run_step(step, None, hooks or None)
    finish([result], None, flags, False)
    if hooks:
        hooks.send("summary", {"results": [result]})
    return 0 if result["outcome"] in ("done", "stopped", "skipped") else 1


def run_target(argv):
    flags, rest = split_run_flags(argv, tuple(RUN_FLAGS))
    if not rest:
        raise spec.ParseError("run what? a preset name, a .tt file, '-' or a quoted line")
    blocks = runner.resolve(" ".join(rest) if len(rest) > 1 else rest[0])
    hooks = runner.Hooks(flags.get("emit"), flags["on"])
    start = int(flags.get("start", 1))
    for block in blocks:
        results, quit = runner.run_block(block, flags.get("view"), hooks or None, start)
        card = finish(results, block, flags, quit)
        if hooks:
            hooks.send("summary", {"preset": block["name"], "results": results, "score": card})
        if quit:
            return 1
        start = 1
    return 0


def list_presets(argv):
    found = runner.presets()
    if argv:
        if argv[0] not in found:
            raise spec.ParseError("no preset named %r" % argv[0])
        block, path = found[argv[0]]
        print("[%s]  from %s" % (block["name"], path))
        for key in ("repeat", "gap", "advance", "score"):
            if block[key] != spec.new_block("")[key]:
                print("@%s %s" % (key, "%gs" % block[key] if key == "gap" else block[key]))
        for step in block["steps"]:
            label = step.get("label")
            print(spec.describe(step) + (' --label "%s"' % label if label else ""))
        return 0
    if not found:
        print("no presets yet. Put [name] blocks in ~/.config/timetools/*.tt or ./*.tt")
        return 0
    width = max(len(n) for n in found)
    for name, (block, path) in found.items():
        steps = len(spec.expand(block))
        print("%-*s  %2d step%s  %s" % (width, name, steps, "" if steps == 1 else "s", os.path.basename(path)))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    prog = os.path.basename(sys.argv[0]) if sys.argv and sys.argv[0] else "tt"
    if prog in ("__main__.py", "-c", "tt.py"):
        prog = "tt"
    if prog in spec.TOOLS:  # installed as `timer`, `fireworks`, ...
        argv, prog = [prog] + argv, "tt"
    try:
        if not argv:
            if sys.stdin.isatty() and sys.stdout.isatty():
                from timetools import menu
                return menu.run()
            print(spec.help_text(None, prog))
            return 0
        command, rest = argv[0], argv[1:]
        if command in ("-h", "--help", "help"):
            tool = spec.ALIASES.get(rest[0], rest[0]) if rest else None
            if tool and tool not in spec.TOOLS:
                raise spec.ParseError("unknown tool %r" % rest[0])
            print(spec.help_text(tool, prog))
            return 0
        if command in ("-V", "--version"):
            print("timetools " + __version__)
            return 0
        if command == "run":
            return run_target(rest)
        if command == "presets":
            return list_presets(rest)
        if command == "views":
            for name, doc in views.available():
                print("%-10s %s" % (name, doc))
            return 0
        return run_tool(argv, prog)
    except (spec.ParseError, views.ViewError) as e:
        print("%s: %s" % (prog, e), file=sys.stderr)
        return 2
    except BrokenPipeError:  # e.g. piped into head
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    except OSError as e:
        print("%s: %s" % (prog, e), file=sys.stderr)
        return 2
