// node --test web/test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import tt, { Rand, parseLine, parseText, expand, plan, stream, score, fmt, status, run, define, presets, timer, stopwatch, metronome, counter, fireworks, wait } from "./timetools.js";

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const CASES = JSON.parse(readFileSync(join(ROOT, "spec", "cases.json"), "utf8"));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("lines parse as spec/cases.json says", () => {
  for (const c of CASES.parse) {
    if (c.want === null) assert.throws(() => parseLine(c.line), tt.ParseError, c.line);
    else assert.deepEqual(parseLine(c.line), c.want, c.line);
  }
});

test("preset text parses as spec/cases.json says", () => {
  for (const c of CASES.text) {
    if (c.want === null) assert.throws(() => parseText(c.text), tt.ParseError);
    else assert.deepEqual(parseText(c.text).map((b) => ({ ...b, steps: expand(b) })), c.want);
  }
});

test("scorecards match spec/cases.json", () => {
  for (const c of CASES.score) {
    const results = c.times.map((t, i) => ({ tool: "stopwatch", label: `Solve ${i + 1}`, outcome: t === null ? "dnf" : "done", elapsed: t === null ? 120 : t }));
    assert.deepEqual(score(results, c.kind), c.want);
  }
});

test("a seed gives the same bursts as the Python CLI", () => {
  const py = `
import json, sys, itertools
sys.path.insert(0, ${JSON.stringify(join(ROOT, "py"))})
from timetools import spec
from timetools.fireworks import Rand, plan, stream
out = []
for c in json.loads(sys.argv[1]):
    line = "fireworks %s --seed %d" % (c["span"], c["seed"])
    for k in ("count", "rate", "spread", "cluster", "within"):
        if k in c: line += " --%s %s" % (k, c[k])
    s = spec.parse_line(line)
    cfg = dict(spec.DEFAULTS["fireworks"], **s)
    if cfg["span"] == "forever":
        out.append(list(itertools.islice(stream(cfg["rate"], cfg["spread"], Rand(c["seed"]), cfg["cluster"], cfg["within"]), c["first"])))
    else:
        rate = cfg["rate"] or (None if cfg["count"] else [1.0, 1.0])
        out.append(list(plan(cfg["span"], cfg["count"], rate, cfg["spread"], Rand(c["seed"]), cfg["cluster"], cfg["within"])))
print(json.dumps(out))`;
  const want = JSON.parse(execFileSync("python3", ["-c", py, JSON.stringify(CASES.plan)], { encoding: "utf8" }));
  const r = new Rand(1);
  assert.deepEqual([r.next(), r.next(), r.next()].map((x) => +x.toFixed(10)), [0.6270739406, 0.0027357212, 0.52744704]);
  CASES.plan.forEach((c, i) => {
    let line = `fireworks ${c.span} --seed ${c.seed}`;
    for (const k of ["count", "rate", "spread", "cluster", "within"]) if (k in c) line += ` --${k} ${c[k]}`;
    const step = parseLine(line);
    if (c.span === "forever") {
      const it = stream(step), got = Array.from({ length: c.first }, () => it.next().value);
      assert.deepEqual(got, want[i], line);
    } else {
      const got = plan(step);
      assert.deepEqual([got.span, got.times], want[i], line);
    }
  });
});

test("format matches the CLI", () => {
  assert.equal(fmt(65.9), "01:05");
  assert.equal(fmt(65.1, { ceil: true }), "01:06");
  assert.equal(fmt(3723.456, { decimals: 2 }), "1:02:03.45");
  assert.equal(status({ tool: "metronome", bpm: 96, beats: 3, pos: 1, label: "" }), "96 bpm ○●○");
});

test("tools: timer, wait, stopwatch cap, metronome --for, counter", async () => {
  const t = await timer("0.12s", { label: "tea", sound: false }).done;
  assert.deepEqual([t.outcome, t.label], ["done", "tea"]);
  assert.equal((await wait("0.05s").done).tool, "wait");
  const sw = await stopwatch({ cap: "0.1s", label: "Solve" }).done;
  assert.deepEqual([sw.outcome, sw.elapsed], ["dnf", 0.1]);
  const m = await metronome(400, { for: "0.4s", sound: false }).done;
  assert.equal(m.outcome, "done");
  assert.ok(m.beats >= 2 && m.beats <= 4, String(m.beats));
  const c = counter({ start: 10, step: 2, autostart: false });
  const seen = [];
  c.on("change", (s) => seen.push(s.n));
  c.add().add().undo().add(5).reset();
  assert.deepEqual(seen, [12, 14, 12, 17, 10]);
});

test("fireworks: clusters and forever shows run headless", async () => {
  const show = fireworks({ span: "0.3s", count: 3, spread: "even", cluster: "2-2", within: "0.01s", seed: 1 });
  let bursts = 0;
  show.on("burst", () => bursts++);
  const r = await show.done;
  assert.equal(bursts, r.count);
  assert.equal(r.fired, 6);
  const forever = fireworks({ span: "forever", rate: "20/s", seed: 2 });
  await sleep(300);
  forever.stop();
  const f = await forever.done;
  assert.equal(f.count, null);
  assert.ok(f.fired > 2, String(f.fired));
});

test("runs: presets play in order with repeats, gaps and scores", async () => {
  define("[drill]\n@repeat 2\n@gap 0.05s\n@score times\nwait 0.05s --label 'Rest {n}'\nstopwatch --cap 0.05s --label 'Solve {n}'");
  assert.deepEqual(presets().map((p) => [p.name, p.steps]), [["drill", 4]]);
  const r = run("drill");
  const steps = [];
  let card = null;
  r.on("step", (s) => steps.push(s.label));
  r.on("summary", (s) => { card = s.score; });
  const results = await r.done;
  assert.deepEqual(steps, ["Rest 1", "next: Solve 1", "Solve 1", "next: Rest 2", "Rest 2", "next: Solve 2", "Solve 2"].filter((l) => !l.startsWith("next")));
  assert.deepEqual(results.map((x) => x.label), ["Rest 1", "Solve 1", "Rest 2", "Solve 2"]);
  assert.deepEqual(card.solves.map((s) => s.time), [null, null]);
});

test("runs: next, back and stop steer the run; @advance key waits", async () => {
  const r = run("@advance key; timer 5s --label one --no-sound; timer 5s --label two --no-sound; timer 5s --label three --no-sound");
  const seen = [];
  r.on("step", (s) => seen.push(s.label));
  r.on("ready", () => setTimeout(() => r.next(), 10));
  await sleep(30); r.next();          // skip one
  await sleep(60); r.back();          // two -> back to one
  await sleep(60); r.stop();
  const results = await r.done;
  assert.deepEqual(seen, ["one", "two", "one"]);
  assert.deepEqual(results.map((x) => [x.label, x.nav]), [["one", "quit"], ["two", "back"]]);
});

test("errors name the problem", () => {
  assert.throws(() => metronome(999), /bpm must be between/);
  assert.throws(() => parseLine("timer"), /needs a duration/);
  assert.throws(() => run("nosuchpreset"), /no preset named/);
});
