"""Find and load views.

The default view is `plain`. Any other view loads only when asked for, by
`--view NAME` or TIMETOOLS_VIEW, so the default path never imports it. NAME
can be:
  a built-in        big
  an entry point    in the `timetools.views` group of any installed package
  a module path     mypkg.myview or mypkg.myview:FancyView
  a file            ./myview.py
A module that names no class must define `View`.
"""

import importlib
import os
import sys

DEFAULT = "plain"
BUILTIN = ("plain", "big", "none")
GROUP = "timetools.views"


class ViewError(Exception):
    pass


def load(name=None, style=None):
    name = name or os.environ.get("TIMETOOLS_VIEW") or DEFAULT
    view = _make(_resolve(name), style)
    if name == DEFAULT:
        return view
    if getattr(view, "needs_tty", False) and not sys.stdout.isatty():
        return _plain()
    return Guarded(view, name)


def _make(cls, style):
    try:
        return cls(style=style)
    except TypeError:  # a view that takes no style
        return cls()


def available():
    """(name, first doc line) for every view that can be found."""
    found = []
    for name in BUILTIN + tuple(ep.name for ep in _entry_points()):
        try:
            cls = _resolve(name)
            doc = (sys.modules[cls.__module__].__doc__ or "").strip().splitlines()
            found.append((name, doc[0] if doc else ""))
        except Exception as e:  # a broken add-on must not hide the others
            found.append((name, "failed to load: %s" % e))
    return found


def _plain():
    from timetools.views.plain import View
    return View()


def _entry_points():
    from importlib import metadata
    eps = metadata.entry_points()
    return eps.select(group=GROUP) if hasattr(eps, "select") else eps.get(GROUP, [])


def _resolve(name):
    try:
        if name in BUILTIN:
            return importlib.import_module("timetools.views." + name).View
        if name.endswith(".py"):
            from importlib.util import module_from_spec, spec_from_file_location
            spec = spec_from_file_location("timetools_view_file", name)
            if spec is None or not os.path.exists(name):
                raise ViewError("no such file: %s" % name)
            module = module_from_spec(spec)
            spec.loader.exec_module(module)
            return module.View
        for ep in _entry_points():
            if ep.name == name:
                return _class_of(ep.load())
        modname, _, attr = name.partition(":")
        if "." in modname or attr:
            module = importlib.import_module(modname)
            return getattr(module, attr) if attr else module.View
    except ViewError:
        raise
    except Exception as e:
        raise ViewError("can't load view %r: %s" % (name, e))
    raise ViewError("unknown view %r (try: %s)" % (name, ", ".join(n for n, _ in available())))


def _class_of(obj):
    return obj.View if hasattr(obj, "View") and not isinstance(obj, type) else obj


class Guarded:
    """Wraps an add-on view. If it raises, the terminal is restored and the
    plain view takes over, so a broken view can't stop a timer."""

    def __init__(self, view, name):
        self._view, self._name = view, name
        self._opened = None
        self._fell_back = False

    def _call(self, method, *args):
        try:
            return getattr(self._view, method)(*args)
        except Exception as e:
            if self._fell_back:
                raise
            try:
                self._view.abort()
            except Exception:
                pass
            sys.stderr.write("\nview %r failed (%s: %s), using plain\n" % (self._name, type(e).__name__, e))
            self._view, self._fell_back = _plain(), True
            if self._opened is not None and method != "open":
                self._view.open(*self._opened)
            return getattr(self._view, method)(*args)

    def open(self, tool, help):
        self._opened = (tool, help)
        return self._call("open", tool, help)

    def frame(self, state):
        return self._call("frame", state)

    def next_frame(self, state):
        return self._call("next_frame", state)

    def event(self, name, state):
        return self._call("event", name, state)

    def close(self, state):
        return self._call("close", state)

    def abort(self):
        return self._call("abort")
