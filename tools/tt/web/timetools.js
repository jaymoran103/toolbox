// timetools.js: time tools for the browser and Node. One file, no deps.
//
// The same tools, line syntax and presets as the tt CLI. SPEC.md has the
// grammar, and spec/cases.json holds the cases both must agree on.
//
//   import tt from "./timetools.js";
//   tt.run("metronome 96 --for 4m -b 3; wait 10s; metronome 120 --for 3m");
//   tt.fireworks({ span: "10s", count: "20-30" }).on("burst", (s) => ...);
//
// Markup works with no script of your own:
//   <button data-tt-run="setlist">Play the set</button>
//   <button data-tt="fireworks" data-tt-span="5s" data-tt-rate="2-4/s">Go</button>

const HAS_DOM = typeof document !== "undefined";
const now = () => performance.now() / 1000;

// ---------------------------------------------------------------- random

/** Seeded mulberry32. Bit for bit the same stream as the CLI's Rand. */
export class Rand {
  constructor(seed) {
    this.seed = seed == null ? (Math.random() * 4294967296) >>> 0 : seed >>> 0;
    this.a = this.seed;
  }
  next() {
    this.a = (this.a + 0x6d2b79f5) >>> 0;
    const a = this.a;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }
  uniform(a, b) { return a + (b - a) * this.next(); }
  randint(a, b) { return a + Math.floor(this.next() * (b - a + 1)); }
  choice(list) { return list[Math.floor(this.next() * list.length)]; }
}

// ---------------------------------------------------------------- values

export class ParseError extends Error {}

const UNITS = { h: 3600, m: 60, s: 1 };
const NUMBER = /^\d+(\.\d+)?$/;

/** '90', '90s', '5m', '1h30m', '2.5m', '1:30', '1:02:03' -> seconds. Numbers pass through. */
export function parseDuration(text) {
  if (typeof text === "number") return text;
  const t = String(text).trim().toLowerCase().replace(/ /g, "");
  if (!t) throw new ParseError("empty duration");
  if (t.includes(":")) {
    const parts = t.split(":");
    if (parts.length > 3 || !parts.every((p) => NUMBER.test(p))) throw new ParseError(`can't read duration: ${text}`);
    return parts.reduce((total, p) => total * 60 + parseFloat(p), 0);
  }
  if (NUMBER.test(t)) return parseFloat(t);
  let total = 0, pos = 0;
  for (const m of t.matchAll(/(\d+(?:\.\d+)?)([hms])/g)) {
    if (m.index !== pos) break;
    total += parseFloat(m[1]) * UNITS[m[2]];
    pos = m.index + m[0].length;
  }
  if (pos === 0 || pos !== t.length) throw new ParseError(`can't read duration: ${text}`);
  return total;
}

/** '5', '5-10', '1-2m' -> [lo, hi]. In '1-2m' the high end's unit also applies to a bare low end. */
export function parseRange(text, one) {
  if (Array.isArray(text)) return [one(text[0]), one(text[1] ?? text[0])];
  if (typeof text === "number") return [text, text];
  let [lo, hi = ""] = String(text).trim().split(/-(.*)/s);
  const unit = hi.toLowerCase().match(/[a-z]+$/);
  if (unit && NUMBER.test(lo.trim())) lo += unit[0];
  const range = [one(lo), hi ? one(hi) : one(lo)];
  if (range[1] < range[0]) throw new ParseError(`range ${text} runs backwards`);
  return range;
}

const RATE_UNITS = { s: 1, sec: 1, m: 60, min: 60, h: 3600, hr: 3600 };

/** '2', '2/s', '30/m', '1-3/s' -> [lo, hi] per second. */
export function parseRate(text) {
  if (typeof text === "number") return [text, text];
  if (Array.isArray(text)) return text;
  const [body, unit = ""] = String(text).trim().split(/\/(.*)/s);
  if (unit && !(unit in RATE_UNITS)) throw new ParseError(`unknown rate unit ${unit} (use s, m or h)`);
  return parseRange(body, toFloat).map((r) => r / RATE_UNITS[unit || "s"]);
}

function toInt(text) {
  if (typeof text === "number" && Number.isInteger(text)) return text;
  if (!/^-?\d+$/.test(String(text).trim())) throw new ParseError(`not a whole number: ${text}`);
  return parseInt(text, 10);
}

function toFloat(text) {
  if (typeof text === "number") return text;
  if (!/^-?\d+(\.\d+)?$/.test(String(text).trim())) throw new ParseError(`not a number: ${text}`);
  return parseFloat(text);
}

function toBool(text) {
  if (typeof text === "boolean") return text;
  const v = String(text).toLowerCase();
  if (["true", "yes", "on", "1"].includes(v)) return true;
  if (["false", "no", "off", "0"].includes(v)) return false;
  throw new ParseError(`not true or false: ${text}`);
}

function convert(kind, text) {
  switch (kind) {
    case "str": return String(text);
    case "int": return toInt(text);
    case "float": return toFloat(text);
    case "flag": return toBool(text);
    case "count": { const n = toInt(text); if (n < 1) throw new ParseError("must be 1 or more"); return n; }
    case "dur": return parseDuration(text);
    case "dur*": return text === "forever" ? "forever" : parseDuration(text);
    case "span": return text === "forever" ? "forever" : parseRange(text, parseDuration);
    case "irange": return parseRange(text, toInt);
    case "rate": return parseRate(text);
  }
  const options = kind.slice(7).split("|");
  if (!options.includes(text)) throw new ParseError(`use one of ${options.join(", ")}`);
  return text;
}

// ---------------------------------------------------------------- syntax

const ALIASES = { sw: "stopwatch", t: "timer", m: "metronome", c: "counter", fw: "fireworks" };

// name: [kind, short flag]. The CLI's spec.py holds the same table, plus help text.
const COMMON = { label: ["str"], view: ["str"], target: ["str"], trigger: ["str"], origin: ["str"] };
const STYLE = {
  palette: ["choice:festival|ember|frost|gold"], colors: ["str"], children: ["int"], trail: ["int"],
  length: ["float"], size: ["float"], gravity: ["float"], crackle: ["int"], rocket: ["flag"],
};
const TOOLS = {
  stopwatch: { pos: [], opts: { for: ["dur*"], cap: ["dur"], solve: ["flag"] } },
  timer: { pos: ["duration", "label"], need: ["duration"], opts: { duration: ["dur"], rings: ["int"], sound: ["flag"] } },
  wait: { pos: ["duration"], need: ["duration"], opts: { duration: ["dur"] } },
  metronome: { pos: ["bpm"], opts: { bpm: ["int"], beats: ["int", "b"], for: ["dur*"], sound: ["flag"] } },
  counter: { pos: ["label"], opts: { start: ["int"], step: ["int"] } },
  fireworks: {
    pos: ["span"],
    opts: {
      span: ["span"], count: ["irange", "n"], rate: ["rate", "r"], spread: ["choice:random|even"], seed: ["int"],
      cluster: ["irange"], within: ["dur"], sound: ["flag"], ...STYLE,
    },
  },
};
export const DEFAULTS = {
  stopwatch: { for: null, cap: null, solve: false },
  timer: { rings: 3, sound: true },
  wait: {},
  metronome: { bpm: 120, beats: 4, for: null, sound: true },
  counter: { start: 0, step: 1 },
  fireworks: { span: [30, 30], count: null, rate: null, spread: "random", seed: null, cluster: null, within: 2, sound: false },
};
const DIRECTIVES = { repeat: "count", gap: "dur", advance: "choice:auto|key", score: "choice:times|wca" };

const schema = (tool) => ({ ...COMMON, ...TOOLS[tool].opts });

/**
 * Split a line into statements of tokens. Quotes group words, ';' ends a
 * statement, and '#' starts a comment at the start of a line or when a space
 * follows it, so '#ff3366' stays a value.
 */
export function tokenize(line) {
  const statements = [];
  let tokens = [], cur = "", has = false, i = 0;
  const n = line.length;
  const flush = () => { if (has) tokens.push(cur); cur = ""; has = false; };
  while (i < n) {
    const ch = line[i];
    if (ch === " " || ch === "\t") { flush(); i++; }
    else if (ch === "#" && !has && (!line.slice(0, i).trim() || i + 1 === n || line[i + 1] === " " || line[i + 1] === "\t")) break;
    else if (ch === ";") { flush(); statements.push(tokens); tokens = []; i++; }
    else if (ch === "'") {
      const end = line.indexOf("'", i + 1);
      if (end < 0) throw new ParseError("unclosed quote");
      cur += line.slice(i + 1, end); has = true; i = end + 1;
    } else if (ch === '"') {
      has = true; i++;
      for (;;) {
        if (i >= n) throw new ParseError("unclosed quote");
        const c = line[i];
        if (c === "\\" && i + 1 < n && (line[i + 1] === '"' || line[i + 1] === "\\")) { cur += line[i + 1]; i += 2; }
        else if (c === '"') { i++; break; }
        else { cur += c; i++; }
      }
    } else { cur += ch; has = true; i++; }
  }
  flush();
  statements.push(tokens);
  return statements.filter((s) => s.length);
}

/** Tokens of one statement -> { tool, option: value }. Only given options appear. */
export function parseStep(tokens) {
  const toks = [...tokens];
  if (toks[0] === "tt") toks.shift();
  if (!toks.length) throw new ParseError("empty step");
  const tool = ALIASES[toks[0]] || toks[0];
  if (!TOOLS[tool]) throw new ParseError(`unknown tool ${toks[0]}`);
  const opts = schema(tool);
  const shorts = Object.fromEntries(Object.entries(opts).filter(([, s]) => s[1]).map(([k, s]) => [s[1], k]));
  const pos = [...TOOLS[tool].pos];
  const out = { tool };
  let i = 1;
  while (i < toks.length) {
    const tok = toks[i++];
    let name, value = null;
    if (tok.startsWith("--") && tok.length > 2) {
      const eq = tok.indexOf("=");
      name = eq < 0 ? tok.slice(2) : tok.slice(2, eq);
      if (eq >= 0) value = tok.slice(eq + 1);
      if (!opts[name] && name.startsWith("no-") && opts[name.slice(3)]?.[0] === "flag") {
        if (value !== null) throw new ParseError(`--${name} takes no value`);
        name = name.slice(3); value = "false";
      }
      if (!opts[name]) throw new ParseError(`unknown option --${name} for ${tool}`);
    } else if (/^-[A-Za-z]$/.test(tok)) {
      name = shorts[tok[1]];
      if (!name) throw new ParseError(`unknown option ${tok} for ${tool}`);
    } else {
      if (!pos.length) throw new ParseError(`unexpected ${tok} for ${tool}`);
      name = pos[0]; value = tok;
    }
    const kind = opts[name][0];
    if (kind === "flag" && value === null) value = "true";
    if (value === null) {
      if (i >= toks.length) throw new ParseError(`--${name} needs a value`);
      value = toks[i++];
    }
    try { out[name] = convert(kind, value); }
    catch (e) { throw new ParseError(`bad value for ${name}: ${e.message}`); }
    const at = pos.indexOf(name);
    if (at >= 0) pos.splice(at, 1);
  }
  for (const name of TOOLS[tool].need || []) if (!(name in out)) throw new ParseError(`${tool} needs a ${name}`);
  if ("count" in out && "rate" in out) throw new ParseError("give count or rate, not both");
  if (out.span === "forever" && "count" in out) throw new ParseError("a forever show takes a rate, not a count");
  return out;
}

export function parseLine(line) {
  const statements = tokenize(line);
  if (statements.length !== 1) throw new ParseError("expected one step");
  return parseStep(statements[0]);
}

const newBlock = (name) => ({ name, repeat: 1, gap: 0, advance: "auto", score: null, steps: [] });

/** Preset text -> blocks. Steps before any [name] form a block named "". */
export function parseText(text) {
  const blocks = [newBlock("")];
  String(text).split(/\r?\n/).forEach((raw, index) => {
    try {
      const header = raw.match(/^\s*\[([A-Za-z0-9_-]+)\]\s*(#.*)?$/);
      if (header) { blocks.push(newBlock(header[1])); return; }
      for (const statement of tokenize(raw)) {
        if (statement[0].startsWith("@")) {
          const name = statement[0].slice(1);
          if (!DIRECTIVES[name]) throw new ParseError(`unknown directive @${name}`);
          if (statement.length !== 2) throw new ParseError(`@${name} takes one value`);
          try { blocks[blocks.length - 1][name] = convert(DIRECTIVES[name], statement[1]); }
          catch (e) { throw new ParseError(`bad value for @${name}: ${e.message}`); }
        } else {
          blocks[blocks.length - 1].steps.push(parseStep(statement));
        }
      }
    } catch (e) {
      throw new ParseError(`line ${index + 1}: ${e.message}`);
    }
  });
  const first = blocks[0];
  if (blocks.length > 1 && !first.steps.length && JSON.stringify(first) === JSON.stringify(newBlock(""))) blocks.shift();
  return blocks;
}

/** A block's steps, repeated, with {n} in labels set to the round. */
export function expand(block) {
  const out = [];
  for (let n = 1; n <= block.repeat; n++) {
    for (const step of block.steps) out.push("label" in step ? { ...step, label: step.label.replaceAll("{n}", String(n)) } : { ...step });
  }
  return out;
}

/** A step back as a short line, for menus. */
export function describe(step) {
  const words = [step.tool];
  for (const [key, value] of Object.entries(step)) {
    if (key === "tool" || key === "label") continue;
    if (value === true) words.push(`--${key}`);
    else if (Array.isArray(value)) words.push(`--${key} ${value[0] === value[1] ? value[0] : value.join("-")}`);
    else words.push(`--${key} ${value}`);
  }
  return words.join(" ");
}

/** Raw options from JS or markup -> a full config, read the same way as a line. */
function configure(tool, opts = {}) {
  const kinds = schema(tool);
  const cfg = { ...DEFAULTS[tool], label: "", tool };
  for (const [key, value] of Object.entries(opts)) {
    if (value == null) continue;
    const kind = kinds[key]?.[0];
    cfg[key] = !kind || typeof value === "object" || (typeof value !== "string" && kind !== "span" && kind !== "irange" && kind !== "rate")
      ? value
      : convert(kind, value);
  }
  return cfg;
}

// ---------------------------------------------------------------- format

export function fmt(seconds, { decimals = 0, ceil = false } = {}) {
  seconds = Math.max(0, seconds);
  let whole, frac = null;
  if (decimals) {
    const scale = 10 ** decimals, total = Math.floor(seconds * scale);
    whole = Math.floor(total / scale);
    frac = total % scale;
  } else {
    whole = ceil ? Math.ceil(seconds) : Math.floor(seconds);
  }
  const h = Math.floor(whole / 3600), m = Math.floor((whole % 3600) / 60), s = whole % 60;
  const pad = (n) => String(n).padStart(2, "0");
  let out = h ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
  if (frac !== null) out += "." + String(frac).padStart(decimals, "0");
  return out;
}

/** One line of text for any state. The `text` view shows this. */
export function status(s) {
  let text = "";
  switch (s.tool) {
    case "stopwatch": text = s.outcome === "dnf" ? "DNF" : fmt(s.elapsed, { decimals: 2 }); break;
    case "timer": case "wait": text = s.outcome === "done" ? "done" : fmt(s.left, { ceil: true }); break;
    case "metronome": text = `${s.bpm} bpm ` + Array.from({ length: s.beats }, (_, i) => (i === s.pos ? "●" : "○")).join(""); break;
    case "counter": text = String(s.n); break;
    case "fireworks": text = s.count == null ? `✦ ${s.fired}` : `✦ ${s.fired}/${s.count}`; break;
  }
  return s.label ? `${s.label}  ${text}` : text;
}

// ---------------------------------------------------------------- scheduling

function clusters(times, rng, cluster, within, limit = null) {
  if (!cluster) return [...times];
  const out = [];
  for (const t of times) {
    const size = rng.randint(...cluster);
    const offs = Array.from({ length: size }, () => rng.uniform(0, within)).sort((a, b) => a - b);
    for (const off of offs) if (limit === null || t + off <= limit) out.push(t + off);
  }
  return out.sort((a, b) => a - b);
}

/** Pick a timespan and a burst count from their ranges, then the burst times. */
export function plan(opts = {}) {
  const c = configure("fireworks", opts);
  const rng = opts.rng || new Rand(c.seed);
  if (c.span === "forever") throw new ParseError("a forever show has no plan; use stream()");
  const rate = c.count ? null : c.rate || [1, 1];
  const seconds = rng.uniform(...c.span);
  const n = c.count ? rng.randint(...c.count) : Math.max(1, Math.floor(rng.uniform(...rate) * seconds + 0.5));
  const times = c.spread === "even"
    ? Array.from({ length: n }, (_, i) => ((i + 0.5) * seconds) / n)
    : Array.from({ length: n }, () => rng.uniform(0, seconds)).sort((a, b) => a - b);
  return { span: seconds, times: clusters(times, rng, c.cluster, c.within, seconds), seed: rng.seed };
}

/** Burst times with no end, for a forever show. Gaps are uniform up to twice the mean. */
export function* stream(opts = {}) {
  const c = configure("fireworks", opts);
  const rng = opts.rng || new Rand(c.seed);
  const perSecond = rng.uniform(...(c.rate || [1, 1]));
  let t = 0;
  for (;;) {
    t += c.spread === "even" ? 1 / perSecond : rng.uniform(0, 2 / perSecond);
    yield* clusters([t], rng, c.cluster, c.within);
    if (c.cluster) t += c.within;
  }
}

/** Scorecard for stopwatch results. A capped solve is DNF. The WCA average drops best and worst. */
export function score(results, kind) {
  const solves = results.filter((r) => r.tool === "stopwatch");
  const times = solves.map((r) => (r.outcome === "dnf" ? null : r.elapsed));
  const done = times.filter((t) => t !== null).sort((a, b) => a - b);
  const sum = (list) => list.reduce((a, b) => a + b, 0);
  const card = {
    kind,
    solves: solves.map((r, i) => ({ label: r.label, time: times[i] })),
    best: done.length ? done[0] : null,
    worst: times.includes(null) ? null : done.length ? done[done.length - 1] : null,
    mean: done.length ? sum(done) / done.length : null,
  };
  if (kind === "wca" && times.length >= 3) {
    const dnfs = times.filter((t) => t === null).length;
    if (dnfs > 1) card.average = null;
    else {
      const middle = [...done, ...Array(dnfs).fill(Infinity)].slice(1, -1);
      card.average = sum(middle) / middle.length;
    }
  }
  return card;
}

// ---------------------------------------------------------------- tool base

class Clock {
  constructor() { this.reset(); }
  reset() { this.start = now(); this.pausedAt = null; }
  get paused() { return this.pausedAt !== null; }
  get elapsed() { return (this.pausedAt ?? now()) - this.start; }
  pause() { if (this.pausedAt === null) this.pausedAt = now(); }
  resume() { if (this.pausedAt !== null) { this.start += now() - this.pausedAt; this.pausedAt = null; } }
}

class Tool {
  constructor(cfg) {
    this.tool = cfg.tool;
    this.cfg = cfg;
    this.handlers = {};
    this.clock = new Clock();
    this.running = false;
    this.finished = false;
    this.outcome = null;
    this.nav = null;
    this.timeout = null;
    this.target = resolve(cfg.target);
    this.emitter = resolve(cfg.source) || this.target || (HAS_DOM ? document : null);
    this.view = null;
    this.done = new Promise((ok) => this.on("done", () => ok(this.result())));
    if (cfg.autostart !== false) queueMicrotask(() => { if (!this.running && !this.finished) this.start(); });
  }

  on(name, fn) { (this.handlers[name] ||= []).push(fn); return this; }
  off(name, fn) { this.handlers[name] = (this.handlers[name] || []).filter((f) => f !== fn); return this; }

  emit(name, extra) {
    const s = Object.assign(this.state(), extra);
    for (const fn of this.handlers[name] || []) fn(s);
    if (this.view) this.view.event(name, s);
    if (this.emitter && typeof CustomEvent !== "undefined") {
      this.emitter.dispatchEvent(new CustomEvent("tt:" + name, { detail: s, bubbles: true }));
    }
    return s;
  }

  base() {
    return {
      tool: this.tool, label: this.cfg.label || "", now: now(), elapsed: this.clock.elapsed,
      paused: this.clock.paused, running: this.running, outcome: this.outcome, nav: this.nav,
    };
  }

  /** What the run came to. The same fields as the CLI's results. */
  result() {
    return { tool: this.tool, label: this.cfg.label || "", outcome: this.outcome, nav: this.nav, elapsed: this.clock.elapsed };
  }

  start() {
    if (this.running) return this.resume();
    if (!this.view) this.view = makeView(this);
    this.clock.reset();
    this.running = true;
    this.finished = false;
    this.outcome = this.nav = null;
    this.emit("start", { resumed: false });
    this.begin();
    return this;
  }

  pause() {
    if (!this.running || this.clock.paused) return this;
    this.clock.pause();
    clearTimeout(this.timeout);
    this.halt?.();
    this.emit("pause");
    return this;
  }

  resume() {
    if (!this.running || !this.clock.paused) return this;
    this.clock.resume();
    this.emit("start", { resumed: true });
    this.schedule();
    return this;
  }

  /** Pause or resume, or start again after the tool finished. */
  toggle() {
    if (!this.running) return this.start();
    return this.clock.paused ? this.resume() : this.pause();
  }

  /** End the run. nav is "next", "back" or "quit" when a runner asked. */
  stop(outcome = "stopped", nav = null) {
    if (!this.running) return this;
    clearTimeout(this.timeout);
    this.halt?.();
    this.clock.pause();
    this.running = false;
    this.finished = true;
    this.outcome ||= outcome;
    this.nav = nav;
    this.emit("done", { outcome: this.outcome });
    return this;
  }

  begin() { this.schedule(); }
  schedule() {}

  at(seconds, fn) {
    clearTimeout(this.timeout);
    this.timeout = setTimeout(fn, Math.max(0, seconds * 1000));
  }

  /** Stop when the clock reaches `seconds`, as --for and --cap do. */
  until(seconds, outcome) {
    if (seconds == null || seconds === "forever") return;
    this.at(seconds - this.clock.elapsed, () => {
      if (this.clock.elapsed < seconds - 0.001) return this.until(seconds, outcome);
      this.stop(outcome);
    });
  }
}

// ---------------------------------------------------------------- tools

class Stopwatch extends Tool {
  constructor(cfg) { super(cfg); this.laps = []; }
  state() { return { ...this.base(), laps: [...this.laps], cap: this.cfg.cap }; }
  result() {
    const r = { ...super.result(), laps: [...this.laps] };
    if (this.outcome === "dnf") r.elapsed = this.cfg.cap;
    return r;
  }
  schedule() {
    const { cap } = this.cfg, limit = this.cfg.for;
    if (cap != null && (limit == null || limit === "forever" || cap <= limit)) this.until(cap, "dnf");
    else this.until(limit, "done");
  }
  /** In a solve, stop and submit the time. */
  submit() { return this.stop("done"); }
  lap() {
    if (!this.running) return this;
    this.laps.push(this.clock.elapsed);
    const n = this.laps.length;
    this.emit("lap", { lap: n, split: this.laps[n - 1] - (this.laps[n - 2] || 0) });
    return this;
  }
  reset() {
    const wasPaused = this.clock.paused;
    this.clock.reset();
    if (wasPaused) this.clock.pause();
    this.laps = [];
    this.emit("change", { reset: true });
    this.schedule();
    return this;
  }
}

class Timer extends Tool {
  state() {
    const left = Math.max(0, this.cfg.duration - this.clock.elapsed);
    return { ...this.base(), total: this.cfg.duration, left };
  }
  result() { return { ...super.result(), elapsed: Math.min(this.cfg.duration, this.clock.elapsed), total: this.cfg.duration }; }
  schedule() {
    this.at(this.cfg.duration - this.clock.elapsed, () => {
      if (this.clock.elapsed < this.cfg.duration - 0.001) return this.schedule(); // woke early
      if (this.cfg.sound) chime(this.cfg.rings ?? 3);
      this.stop("done");
    });
  }
  stop(outcome = "cancelled", nav = null) { return super.stop(outcome, nav); }
}

const MIN_BPM = 20, MAX_BPM = 400;

class Metronome extends Tool {
  constructor(cfg) {
    super(cfg);
    this.bpm = cfg.bpm;
    this.beats = Math.max(1, cfg.beats);
    this.count = 0;
    this.played = 0;
    this.taps = [];
    this.gen = 0; // bumped on pause and stop, so queued beats from before are dropped
  }
  state() {
    const pos = this.count && !this.clock.paused ? (this.count - 1) % this.beats : -1;
    return { ...this.base(), bpm: this.bpm, beats: this.beats, count: this.count, pos, interval: 60 / this.bpm };
  }
  result() { return { ...super.result(), bpm: this.bpm, beats: this.played }; }
  begin() { this.count = 0; this.queued = 0; this.nextAt = 0; this.audioAt = null; this.schedule(); }
  schedule() {
    const limit = this.cfg.for;
    if (limit != null && limit !== "forever") {
      clearTimeout(this.endTimer);
      this.endTimer = setTimeout(() => this.stop("done"), Math.max(0, (limit - this.clock.elapsed) * 1000));
    }
    // Until the page has had a click or key, the audio clock stands still,
    // so the timeout path keeps the beat and audio takes over once it runs.
    const ctx = this.cfg.sound ? audio() : null;
    if (ctx && ctx.state === "running") return this.scheduleAudio();
    const elapsed = this.clock.elapsed;
    if (this.nextAt < elapsed - 60 / this.bpm) this.nextAt = elapsed; // fell behind: resync
    this.at(this.nextAt - elapsed, () => {
      if (ctx && ctx.state === "running") click(ctx.currentTime, this.count % this.beats === 0 && this.beats > 1);
      this.beat();
      this.nextAt += 60 / this.bpm;
      this.schedule();
    });
  }
  scheduleAudio() {
    const ctx = audio();
    if (ctx.state !== "running") { this.audioAt = null; this.nextAt = this.clock.elapsed; return this.schedule(); }
    if (this.audioAt === null || this.audioAt < ctx.currentTime) this.audioAt = ctx.currentTime + 0.05;
    const ahead = HAS_DOM && document.hidden ? 1.5 : 0.12;
    const gen = this.gen;
    while (this.audioAt < ctx.currentTime + ahead) {
      const at = this.audioAt;
      click(at, this.queued % this.beats === 0 && this.beats > 1);
      this.queued += 1;
      setTimeout(() => { if (gen === this.gen && this.running) this.beat(); }, (at - ctx.currentTime) * 1000);
      this.audioAt += 60 / this.bpm;
    }
    this.at(0.025, () => this.scheduleAudio());
  }
  halt() { this.audioAt = null; this.gen += 1; clearTimeout(this.endTimer); }
  beat() {
    this.count += 1;
    this.played += 1;
    const pos = (this.count - 1) % this.beats;
    this.emit("beat", { pos, accent: pos === 0 && this.beats > 1 });
  }
  setBpm(bpm) {
    const old = this.bpm;
    this.bpm = Math.max(MIN_BPM, Math.min(MAX_BPM, Math.round(Number(bpm))));
    if (this.bpm !== old && this.running && !this.clock.paused && this.audioAt === null) {
      this.nextAt += 60 / this.bpm - 60 / old;
      this.schedule();
    }
    if (this.bpm !== old) this.emit("change", { bpm: this.bpm });
    return this;
  }
  tap() {
    const t = now();
    this.taps = this.taps.filter((x) => t - x < 2.5).concat(t);
    if (this.taps.length >= 2) {
      const gaps = this.taps.slice(1).map((x, i) => x - this.taps[i]);
      this.setBpm(Math.round((60 * gaps.length) / gaps.reduce((a, b) => a + b, 0)));
    }
    return this;
  }
  resume() { this.audioAt = null; this.queued = 0; this.nextAt = this.clock.elapsed; this.count = 0; return super.resume(); }
}

class Counter extends Tool {
  constructor(cfg) {
    super(cfg);
    this.n = cfg.start;
    this.history = [];
  }
  state() { return { ...this.base(), n: this.n, start: this.cfg.start, step: this.cfg.step }; }
  result() { return { ...super.result(), n: this.n }; }
  add(by = this.cfg.step) { this.history.push(this.n); this.n += by; return this.changed(); }
  undo() { if (this.history.length) this.n = this.history.pop(); return this.changed(); }
  reset() { this.history.push(this.n); this.n = this.cfg.start; return this.changed(); }
  changed() { this.emit("change"); return this; }
  stop(outcome = "done", nav = null) { return super.stop(outcome, nav); }
}

class Fireworks extends Tool {
  constructor(cfg) {
    super(cfg);
    const rng = new Rand(cfg.seed);
    this.seed = rng.seed;
    if (cfg.span === "forever") {
      this.span = Infinity;
      this.times = stream({ ...cfg, rng });
      this.count = null;
    } else {
      const p = plan({ ...cfg, rng });
      this.span = p.span;
      this.times = p.times[Symbol.iterator]();
      this.count = p.times.length;
    }
    this.upcoming = this.times.next().value;
    this.fired = 0;
  }
  state() {
    return {
      ...this.base(), elapsed: Math.min(this.span, this.clock.elapsed), span: this.span,
      count: this.count, fired: this.fired, seed: this.seed, done: this.finished,
    };
  }
  result() { return { ...super.result(), elapsed: Math.min(this.span, this.clock.elapsed), fired: this.fired, count: this.count }; }
  schedule() {
    const elapsed = this.clock.elapsed;
    while (this.upcoming !== undefined && elapsed >= this.upcoming) {
      this.fired += 1;
      this.upcoming = this.times.next().value;
      if (this.cfg.sound) pop();
      this.emit("burst", { index: this.fired - 1 });
    }
    if (elapsed >= this.span) return this.stop("done");
    const next = this.upcoming !== undefined ? this.upcoming : this.span;
    this.at(next - elapsed, () => this.schedule());
  }
}

const CLASSES = { stopwatch: Stopwatch, timer: Timer, wait: Timer, metronome: Metronome, counter: Counter, fireworks: Fireworks };

/** Errors a parser can't see, such as a zero-length timer. The CLI's runner.check matches. */
function check(cfg) {
  for (const key of ["duration", "for", "cap", "within"]) {
    if (typeof cfg[key] === "number" && !(cfg[key] > 0)) return `--${key} must be more than zero`;
  }
  if (cfg.tool === "metronome" && !(cfg.bpm >= MIN_BPM && cfg.bpm <= MAX_BPM)) return `bpm must be between ${MIN_BPM} and ${MAX_BPM}`;
  if (cfg.tool === "fireworks") {
    if (cfg.span !== "forever" && !(cfg.span[0] > 0)) return "span must be more than zero";
    if ((cfg.count || [1])[0] < 1 || (cfg.rate || [1])[0] <= 0) return "count and rate must be more than zero";
  }
  return null;
}

/** A tool from a parsed step or plain options. */
export function make(tool, opts = {}) {
  tool = ALIASES[tool] || tool;
  if (!CLASSES[tool]) throw new ParseError(`unknown tool ${tool}`);
  const cfg = configure(tool, opts);
  if (tool === "wait") Object.assign(cfg, { sound: false, rings: 0 });
  const problem = check(cfg);
  if (problem) throw new ParseError(`${tool}: ${problem}`);
  return new CLASSES[tool](cfg);
}

export const stopwatch = (opts = {}) => make("stopwatch", opts);
export const timer = (duration, opts = {}) => make("timer", { ...opts, duration });
export const wait = (duration, opts = {}) => make("wait", { ...opts, duration });
export const metronome = (bpm = 120, opts = {}) => make("metronome", { ...opts, bpm });
export const counter = (opts = {}) => make("counter", opts);
export const fireworks = (opts = {}) => make("fireworks", opts);

// ---------------------------------------------------------------- presets and runs

const registry = new Map();
const loading = new Set();

/** Add the [name] blocks in some preset text. Returns their names. */
export function define(text) {
  const names = [];
  for (const block of parseText(text)) if (block.name) { registry.set(block.name, block); names.push(block.name); }
  return names;
}

/** Fetch a .tt file and define its presets. */
export function load(url) {
  const p = fetch(url).then((r) => {
    if (!r.ok) throw new Error(`can't load ${url}: ${r.status}`);
    return r.text();
  }).then(define);
  // Runs and menus wait for loads, but a failed file must not stall them.
  const settled = p.catch((e) => console.warn("timetools:", e.message)).finally(() => loading.delete(settled));
  loading.add(settled);
  return p;
}

export function presets() {
  return [...registry.values()].map((b) => ({ name: b.name, steps: expand(b).length, first: b.steps[0] ? describe(b.steps[0]) : "" }));
}

/** Blocks for a preset name, preset text, a single line, or blocks already parsed. */
function blocksFor(target) {
  if (Array.isArray(target)) return target;
  if (registry.has(target)) return [registry.get(target)];
  const text = String(target);
  if (!/[\s;\n]/.test(text.trim()) && !TOOLS[text] && !ALIASES[text]) throw new ParseError(`no preset named ${text}`);
  return parseText(text);
}

/**
 * Run a preset, preset text or a line. Steps run one after another with the
 * block's @repeat, @gap, @advance and @score. Returns a Runner.
 */
export function run(target, opts = {}) {
  return new Runner(target, opts);
}

class Runner {
  constructor(target, opts) {
    this.opts = opts;
    this.handlers = {};
    this.results = [];
    this.current = null;
    this.waiting = null;
    this.quit = false;
    this.target = resolve(opts.target);
    this.emitter = resolve(opts.source) || this.target || (HAS_DOM ? document : null);
    this.onKey = this.onKey.bind(this);
    // With no preset files still loading, a bad target throws right here.
    const blocks = loading.size ? null : blocksFor(target);
    this.done = Promise.all([...loading]).then(() => this.play(blocks || blocksFor(target)));
  }

  on(name, fn) { (this.handlers[name] ||= []).push(fn); return this; }
  off(name, fn) { this.handlers[name] = (this.handlers[name] || []).filter((f) => f !== fn); return this; }

  emit(name, detail) {
    for (const fn of this.handlers[name] || []) fn(detail);
    if (this.emitter && typeof CustomEvent !== "undefined") this.emitter.dispatchEvent(new CustomEvent("tt:" + name, { detail, bubbles: true }));
  }

  async play(blocks) {
    if (HAS_DOM && this.opts.keys !== false) addEventListener("keydown", this.onKey);
    try {
      let start = this.opts.from || 1;
      for (const block of blocks) {
        const results = await this.block(block, start);
        const card = block.score ? score(results, block.score) : null;
        this.emit("summary", { preset: block.name, results, score: card });
        this.results.push(...results);
        if (this.quit) break;
        start = 1;
      }
    } finally {
      if (HAS_DOM) removeEventListener("keydown", this.onKey);
      this.current = null;
    }
    return this.results;
  }

  async block(block, start) {
    const steps = expand(block), results = new Map();
    let i = Math.max(0, start - 1), first = true;
    while (i >= 0 && i < steps.length && !this.quit) {
      const step = steps[i];
      if (!first) {
        const moved = await this.between(block, step);
        if (moved === "quit") { this.quit = true; break; }
        if (moved === "back") { i = Math.max(0, i - 1); continue; }
      }
      first = false;
      this.emit("step", { preset: block.name, step: i + 1, of: steps.length, label: step.label || describe(step), tool: step.tool });
      const result = await this.step(step);
      results.set(i, result);
      if (result.nav === "quit") { this.quit = true; break; }
      i = result.nav === "back" ? Math.max(0, i - 1) : i + 1;
    }
    return [...results.keys()].sort((a, b) => a - b).map((k) => results.get(k));
  }

  step(step) {
    const opts = { ...step, source: this.opts.source };
    const canvasHost = step.tool !== "fireworks" || this.target?.ttCanvas;
    if (!("target" in step) && this.target && canvasHost) opts.target = this.target;
    if (!("view" in step)) opts.view = step.tool === "fireworks" ? "canvas" : opts.target ? "text" : this.opts.view || "none";
    if (this.opts.view === "none") opts.view = "none";
    this.current = make(step.tool, opts);
    return this.current.done;
  }

  between(block, step) {
    const label = step.label || describe(step);
    if (block.advance === "key") {
      if (this.target) this.target.textContent = `next: ${label}`;
      this.emit("ready", { next: label });
      return new Promise((ok) => { this.waiting = ok; });
    }
    if (block.gap) return this.step({ tool: "wait", duration: block.gap, label: `next: ${label}` }).then((r) => r.nav);
    return Promise.resolve(null);
  }

  /** Start the next step when the block waits for a key, or skip ahead. */
  next() {
    if (this.waiting) { const go = this.waiting; this.waiting = null; go(null); }
    else this.current?.stop(undefined, "next");
    return this;
  }
  back() {
    if (this.waiting) { const go = this.waiting; this.waiting = null; go("back"); }
    else this.current?.stop(undefined, "back");
    return this;
  }
  stop() {
    this.quit = true;
    if (this.waiting) { const go = this.waiting; this.waiting = null; go("quit"); }
    else this.current?.stop(undefined, "quit");
    return this;
  }
  pause() { this.current?.pause(); return this; }
  resume() { this.current?.resume(); return this; }

  /** The same keys as the terminal. */
  onKey(e) {
    const el = e.target;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
    const key = e.key === " " ? "space" : e.key, t = this.current, go = this.waiting;
    const action = go ? { space: () => this.next(), Enter: () => this.next() }[key] : t && keyAction(t, key);
    const nav = { n: () => this.next(), b: () => this.back(), q: () => this.stop(), Escape: () => this.stop() }[key];
    const fn = action || nav;
    if (fn) { e.preventDefault(); fn(); }
  }
}

/** A tool's own keys, matching the terminal tools. */
function keyAction(t, key) {
  if (!t.running) return null;
  if (t.tool === "stopwatch" && t.cfg.solve) return { space: () => t.submit(), Enter: () => t.submit() }[key];
  if (t.tool === "wait") return { space: () => t.stop("skipped"), Enter: () => t.stop("skipped") }[key];
  if (t.tool === "counter") {
    return {
      space: () => t.add(), Enter: () => t.add(), ArrowUp: () => t.add(), "+": () => t.add(),
      ArrowDown: () => t.add(-t.cfg.step), "-": () => t.add(-t.cfg.step), u: () => t.undo(), r: () => t.reset(),
    }[key];
  }
  if (t.tool === "stopwatch") return { space: () => t.toggle(), Enter: () => t.lap(), l: () => t.lap(), r: () => t.reset() }[key];
  if (t.tool === "metronome") {
    return {
      space: () => t.toggle(), ArrowUp: () => t.setBpm(t.bpm + 1), ArrowDown: () => t.setBpm(t.bpm - 1),
      ArrowRight: () => t.setBpm(t.bpm + 5), ArrowLeft: () => t.setBpm(t.bpm - 5), t: () => t.tap(),
    }[key];
  }
  return { space: () => t.toggle() }[key];
}

// ---------------------------------------------------------------- sound

let audioCtx = null;

function audio() {
  if (audioCtx) return audioCtx;
  const Ctx = typeof AudioContext !== "undefined" ? AudioContext : globalThis.webkitAudioContext;
  if (!Ctx) return null;
  audioCtx = new Ctx();
  if (HAS_DOM) {
    const wake = () => audioCtx.resume();
    for (const e of ["pointerdown", "keydown"]) addEventListener(e, wake, { capture: true });
  }
  return audioCtx;
}

function tone(at, freq, length, gain) {
  const ctx = audio();
  if (!ctx) return;
  ctx.resume?.();
  const osc = ctx.createOscillator(), amp = ctx.createGain();
  osc.frequency.value = freq;
  amp.gain.setValueAtTime(gain, at);
  amp.gain.exponentialRampToValueAtTime(0.0001, at + length);
  osc.connect(amp).connect(ctx.destination);
  osc.start(at);
  osc.stop(at + length);
}

function click(at, accent) { tone(at, accent ? 1760 : 1100, 0.05, accent ? 0.5 : 0.3); }

function chime(rings) {
  const ctx = audio();
  if (!ctx) return;
  for (let i = 0; i < rings; i++) tone(ctx.currentTime + i * 0.6, 880, 0.5, 0.3);
}

function pop() {
  const ctx = audio();
  if (!ctx) return;
  ctx.resume?.();
  const length = 0.25, buf = ctx.createBuffer(1, Math.floor(ctx.sampleRate * length), ctx.sampleRate);
  const data = buf.getChannelData(0);
  for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / data.length) ** 3;
  const src = ctx.createBufferSource(), amp = ctx.createGain();
  src.buffer = buf;
  amp.gain.value = 0.35;
  src.connect(amp).connect(ctx.destination);
  src.start();
}


// ---------------------------------------------------------------- views

function resolve(target) {
  if (!target || !HAS_DOM) return null;
  return typeof target === "string" ? document.querySelector(target) : target;
}

function makeView(tool) {
  if (!HAS_DOM) return null;
  const name = tool.cfg.view || "none";
  if (name === "text") return new TextView(tool);
  if (name === "canvas") return tool.tool === "fireworks" ? new CanvasView(tool) : null;
  return null; // none, or a terminal-only view such as big
}

/** Writes status(state) into an element. Redraws only while the tab can see it. */
class TextView {
  constructor(tool) {
    this.tool = tool;
    this.el = tool.target || resolve(tool.cfg.source);
    this.loop = this.loop.bind(this);
  }
  draw() { if (this.el) this.el.textContent = status(this.tool.state()); }
  event() {
    this.draw();
    const moving = ["stopwatch", "timer", "wait"].includes(this.tool.tool);
    if (moving && this.tool.running && !this.tool.clock.paused && !this.frame) this.frame = requestAnimationFrame(this.loop);
  }
  loop() {
    this.frame = null;
    this.draw();
    if (this.tool.running && !this.tool.clock.paused) this.frame = requestAnimationFrame(this.loop);
  }
}

const STYLE_KEYS = ["palette", "colors", "children", "trail", "length", "size", "gravity", "crackle", "rocket"];

class CanvasView {
  constructor(tool) {
    this.tool = tool;
    this.stage = Stage.for(tool.target);
    const style = Object.fromEntries(STYLE_KEYS.filter((k) => tool.cfg[k] != null).map((k) => [k, tool.cfg[k]]));
    this.show = new Show(style, tool.seed);
    const o = tool.cfg.origin;
    this.origin = o === "random" ? null : resolve(o && o !== "element" ? o : tool.cfg.source);
  }
  event(name) {
    this.show.paused = this.tool.running && this.tool.clock.paused; // a finished show keeps animating
    if (name === "burst") {
      this.stage.add(this.show);
      this.show.launch(this.origin ? this.stage.pointOf(this.origin) : null);
    }
    if (name === "start" || name === "burst") this.stage.wake();
  }
}

/** One canvas and one animation loop, shared by every show drawn on it. */
class Stage {
  static for(host) {
    const key = host || document.body;
    if (!key.ttStage) key.ttStage = new Stage(host);
    return key.ttStage;
  }

  constructor(host) {
    this.host = host; // null: a fixed overlay on the whole page
    this.shows = new Set();
    this.canvas = null;
    this.frame = null;
    this.last = null;
    this.loop = this.loop.bind(this);
  }

  add(show) { this.shows.add(show); }

  mount() {
    if (this.canvas) return;
    if (this.host && this.host.ttCanvas) { this.canvas = this.host.ttCanvas; return; }
    const c = document.createElement("canvas");
    c.setAttribute("aria-hidden", "true");
    c.style.cssText = "position:fixed;inset:0;width:100vw;height:100vh;pointer-events:none;z-index:2147483000";
    document.body.appendChild(c);
    this.canvas = c;
  }

  pointOf(el) {
    this.mount();
    const r = el.getBoundingClientRect(), c = this.canvas.getBoundingClientRect();
    const dpr = devicePixelRatio || 1;
    return { x: (r.left + r.width / 2 - c.left) * dpr, y: (r.top + r.height / 2 - c.top) * dpr };
  }

  wake() {
    this.mount();
    if (!this.frame) { this.last = null; this.frame = requestAnimationFrame(this.loop); }
  }

  loop(ms) {
    this.frame = null;
    const t = ms / 1000, dt = this.last === null ? 0 : Math.min(0.1, t - this.last);
    this.last = t;
    const c = this.canvas, dpr = devicePixelRatio || 1;
    const w = Math.round(c.clientWidth * dpr), h = Math.round(c.clientHeight * dpr);
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    const ctx = c.getContext("2d");
    ctx.clearRect(0, 0, w, h);
    ctx.globalCompositeOperation = "lighter";
    for (const show of this.shows) {
      show.step(dt, w, h);
      show.draw(ctx, w, h, dpr);
      if (!show.alive()) this.shows.delete(show);
    }
    if ([...this.shows].some((s) => !s.paused)) {
      this.frame = requestAnimationFrame(this.loop);
    } else if (!this.host && !this.shows.size) {
      c.remove(); // the page overlay leaves no trace when idle
      this.canvas = null;
    }
  }
}

const NAMED = {
  pink: [255, 70, 170], cyan: [0, 220, 255], gold: [255, 200, 60], green: [70, 230, 130],
  violet: [150, 90, 255], red: [255, 70, 80], blue: [70, 130, 255], orange: [255, 140, 40], white: [240, 240, 255],
};
const WHITE = NAMED.white, ROCKET = [255, 190, 110];
const STYLE_DEFAULTS = {
  colors: "pink,cyan,gold,green,violet,red", children: 40, trail: 4, length: 1.4,
  size: 0.3, gravity: 1.0, crackle: 0, rocket: true,
};
// The same palettes as the CLI. Single style flags override them.
const PALETTES = {
  festival: {},
  ember: { colors: "orange,red,gold", crackle: 2, gravity: 1.3, size: 0.25, length: 1.6 },
  frost: { colors: "cyan,blue,white", trail: 6, gravity: 0.6, length: 1.8 },
  gold: { colors: "gold,white", crackle: 3, children: 60 },
};
const TRAIL_GAP = 0.035, FLASH = 0.12, MAX_SPARKS = 3000;

function color(name) {
  name = String(name).trim().toLowerCase();
  if (/^#[0-9a-f]{6}$/.test(name)) return [1, 3, 5].map((i) => parseInt(name.slice(i, i + 2), 16));
  return NAMED[name] || null;
}

const mix = (a, b, t) => {
  t = Math.min(1, Math.max(0, t));
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
};
const rgba = (c, a) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a.toFixed(3)})`;

/**
 * Particles for one show. The same motion and the same random draws, in the
 * same order, as the CLI's big view, so a seed lays out the same show.
 */
class Show {
  constructor(style, seed) {
    const { palette, ...own } = style;
    const o = { ...STYLE_DEFAULTS, ...(PALETTES[palette] || {}), ...own };
    this.colors = String(o.colors).split(",").map(color).filter(Boolean);
    if (!this.colors.length) this.colors = [WHITE];
    this.children = Math.max(1, toInt(o.children));
    this.trail = Math.max(0, toInt(o.trail));
    this.length = Math.max(0.2, Number(o.length));
    this.size = Math.max(0.02, Number(o.size));
    this.gravity = Number(o.gravity);
    this.crackle = Math.max(0, toInt(o.crackle));
    this.rocket = o.rocket !== false && o.rocket !== "false";
    this.calm = HAS_DOM && matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    this.rng = new Rand(seed);
    this.clock = 0;
    this.paused = false;
    this.pending = [];
    this.rockets = [];
    this.sparks = [];
    this.flashes = [];
    this.glows = [];
  }

  launch(origin) { this.pending.push(origin); }
  alive() { return this.pending.length || this.rockets.length || this.sparks.length || this.flashes.length || this.glows.length; }

  step(dt, pw, ph) {
    if (!this.paused) this.clock += dt;
    const t = this.clock, rng = this.rng;
    for (const origin of this.pending) {
      const rgb = rng.choice(this.colors);
      const top = Math.max(0.12, this.size * 0.9);
      let x = rng.uniform(0.15, 0.85) * pw, apex = rng.uniform(top, Math.max(top + 0.05, 0.45)) * ph;
      let y0 = ph - 1;
      if (origin) { x = origin.x; y0 = origin.y; }
      if (this.calm) { this.glows.push([x, origin ? origin.y : apex, t, rgb]); continue; }
      if (this.rocket) {
        const drift = rng.uniform(-0.04, 0.04) * pw, rise = rng.uniform(0.6, 0.9);
        if (y0 - apex < 0.05 * ph) this.explode(x, y0, t, rgb, ph); // too close to the top to rise
        else this.rockets.push([x, y0, apex, origin ? 0 : drift, t, rise, rgb]);
      } else {
        this.explode(x, origin ? origin.y : apex, t, rgb, ph);
      }
    }
    this.pending = [];
    this.rockets = this.rockets.filter((r) => {
      if (t - r[4] < r[5]) return true;
      this.explode(r[0] + r[3], r[2], r[4] + r[5], r[6], ph);
      return false;
    });
    const g = this.g(ph), alive = [];
    for (const sp of this.sparks) {
      if (t - sp[4] < sp[5]) { alive.push(sp); continue; }
      if (sp[7] === 0 && this.crackle) {
        const [x, y] = this.pos(sp, sp[5], g), k = 3 / (this.length * 0.35);
        for (let i = 0; i < this.crackle && alive.length < MAX_SPARKS; i++) {
          const a = rng.uniform(0, 2 * Math.PI), v = this.size * ph * 0.12 * k * rng.uniform(0.5, 1.0);
          alive.push([x, y, v * Math.cos(a), v * Math.sin(a), sp[4] + sp[5], this.length * 0.35, mix(sp[6], WHITE, 0.5), 1, k]);
        }
      }
    }
    this.sparks = alive;
    this.flashes = this.flashes.filter((f) => t - f[2] < FLASH);
    this.glows = this.glows.filter((g2) => t - g2[2] < this.length);
  }

  explode(x, y, born, rgb, ph) {
    const rng = this.rng, n = this.children, k = 3 / this.length, reach = this.size * ph * k;
    for (let i = 0; i < n && this.sparks.length < MAX_SPARKS; i++) {
      const a = (2 * Math.PI * i) / n + rng.uniform(-0.15, 0.15), v = reach * rng.uniform(0.7, 1.0);
      const shade = mix(rgb, WHITE, rng.uniform(0, 0.25));
      this.sparks.push([x, y, v * Math.cos(a), v * Math.sin(a), born, this.length * rng.uniform(0.8, 1.1), shade, 0, k]);
    }
    this.flashes.push([x, y, born]);
  }

  g(ph) { return this.gravity * 0.22 * ph; }

  pos(sp, age, g) {
    const k = sp[8], e = 1 - Math.exp(-k * age);
    return [sp[0] + (sp[2] / k) * e, sp[1] + ((sp[3] - g / k) / k) * e + (g / k) * age];
  }

  draw(ctx, pw, ph, dpr) {
    const t = this.clock, g = this.g(ph);
    const width = Math.max(1, 1.6 * dpr * (ph / (900 * dpr)) ** 0.5);
    ctx.lineCap = "round";

    for (const [x, y, born, rgb] of this.glows) {
      const f = (t - born) / this.length, r = this.size * ph * 0.6;
      const grad = ctx.createRadialGradient(x, y, 0, x, y, r);
      grad.addColorStop(0, rgba(rgb, 0.35 * (1 - f)));
      grad.addColorStop(1, rgba(rgb, 0));
      ctx.fillStyle = grad;
      ctx.fillRect(x - r, y - r, 2 * r, 2 * r);
    }

    for (const [x, y, born] of this.flashes) {
      const b = 1 - (t - born) / FLASH, r = 10 * dpr;
      const grad = ctx.createRadialGradient(x, y, 0, x, y, r);
      grad.addColorStop(0, rgba(WHITE, b));
      grad.addColorStop(1, rgba(WHITE, 0));
      ctx.fillStyle = grad;
      ctx.fillRect(x - r, y - r, 2 * r, 2 * r);
    }

    for (const [x, y0, apex, drift, born, rise, rgb] of this.rockets) {
      const pts = [];
      for (let j = 0; j < 4; j++) {
        const u = (t - born) / rise - j * 0.06;
        if (u < 0) break;
        pts.push([x + drift * u, y0 - (y0 - apex) * (1 - (1 - u) ** 2)]);
      }
      for (let j = 1; j < pts.length; j++) this.segment(ctx, pts[j - 1], pts[j], ROCKET, 0.7 - 0.2 * j, width);
      if (pts.length) this.dot(ctx, pts[0], WHITE, 1, width * 1.4);
    }

    for (const sp of this.sparks) {
      const age = t - sp[4];
      if (age < 0) continue;
      const f = age / sp[5];
      if (f > 0.6 && Math.random() < 0.3) continue; // twinkle
      const bright = (1 - f) ** 1.5;
      let prev = this.pos(sp, age, g);
      this.dot(ctx, prev, mix(sp[6], WHITE, Math.max(0, 0.7 - age * 4)), bright, width * 1.2);
      for (let j = 1; j <= this.trail; j++) {
        const a = age - j * TRAIL_GAP;
        if (a < 0) break;
        const cur = this.pos(sp, a, g);
        this.segment(ctx, prev, cur, sp[6], bright * (1 - j / (this.trail + 1)), width);
        prev = cur;
      }
    }
  }

  segment(ctx, a, b, rgb, alpha, width) {
    ctx.strokeStyle = rgba(rgb, alpha);
    ctx.lineWidth = width;
    ctx.beginPath();
    ctx.moveTo(a[0], a[1]);
    ctx.lineTo(b[0], b[1]);
    ctx.stroke();
  }

  dot(ctx, p, rgb, alpha, size) {
    ctx.fillStyle = rgba(rgb, alpha);
    ctx.fillRect(p[0] - size / 2, p[1] - size / 2, size, size);
  }
}

// ---------------------------------------------------------------- markup

/** Attributes -> line tokens, so markup reads the same way as a line. */
function tokensFrom(el, plain = false) {
  const tokens = [];
  for (const attr of el.attributes) {
    let name = attr.name;
    if (name.startsWith("data-tt-")) name = name.slice(8);
    else if (!plain || ["class", "style", "id", "slot", "trigger"].includes(name) || name.startsWith("data-") || name.startsWith("aria-")) continue;
    if (name === "run" || name === "trigger") continue;
    if (attr.value === "" || attr.value === "true") tokens.push(`--${name}`);
    else if (attr.value === "false") tokens.push(`--no-${name}`);
    else tokens.push(`--${name}`, attr.value);
  }
  return tokens;
}

function bind(el) {
  if (el.ttBound) return;
  el.ttBound = true;
  const when = el.dataset.ttTrigger || "click";
  if (el.dataset.ttRun !== undefined) {
    const go = () => {
      if (el.ttRunner && !el.ttRunner.finished) return el.ttRunner.next();
      el.ttRunner = run(el.dataset.ttRun, { source: el, target: el.dataset.ttTarget });
      el.ttRunner.done.catch((e) => console.warn("timetools:", e.message)).finally(() => { el.ttRunner.finished = true; });
    };
    return trigger(el, when, go);
  }
  let step;
  try {
    step = parseStep([el.dataset.tt, ...tokensFrom(el)]);
  } catch (e) {
    return console.warn(`timetools: ${e.message}`, el);
  }
  const name = step.tool;
  const opts = { ...step, source: el };
  if (!opts.view) opts.view = name === "fireworks" ? "canvas" : opts.target ? "text" : "none";
  const fire = () => {
    try {
      if (name === "fireworks") return make(name, opts);
      if (name === "counter") return (el.ttTool ||= make(name, opts)).add();
      if (!el.ttTool) el.ttTool = make(name, opts);
      else el.ttTool.toggle();
    } catch (e) {
      console.warn("timetools:", e.message);
    }
  };
  if (name === "counter") el.ttTool = make(name, opts); // show the starting value
  trigger(el, when, fire);
}

function trigger(el, when, fire) {
  if (when === "load") fire();
  else if (when === "visible" && typeof IntersectionObserver !== "undefined") {
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) { io.disconnect(); fire(); }
    });
    io.observe(el);
  } else if (when === "click") el.addEventListener("click", fire);
}

/** Read preset scripts and bind [data-tt] and [data-tt-run] under root. Runs on load and for nodes added later. */
export function scan(root = document) {
  const scripts = [...(root.matches?.('script[type="text/tt"]') ? [root] : []), ...(root.querySelectorAll?.('script[type="text/tt"]') || [])];
  for (const s of scripts) {
    if (s.ttRead) continue;
    s.ttRead = true;
    try { s.src ? load(s.src).catch(() => {}) : define(s.textContent); } catch (e) { console.warn("timetools:", e.message); }
  }
  const sel = "[data-tt],[data-tt-run]";
  if (root.matches?.(sel)) bind(root);
  root.querySelectorAll?.(sel).forEach(bind);
}

const MENU_CSS = `:host{display:block}
.list{display:flex;flex-wrap:wrap;gap:8px}
button{font:inherit;color:inherit;background:transparent;border:1px solid currentColor;border-radius:6px;padding:6px 12px;cursor:pointer;opacity:.8}
button:hover,button:focus-visible{opacity:1}
.step{margin-top:12px;opacity:.7}
.readout{font-variant-numeric:tabular-nums;font-size:1.6em;min-height:1.4em}
.controls{display:none;gap:8px;margin-top:8px}
:host([running]) .controls{display:flex}
table{border-collapse:collapse;margin-top:10px;font-variant-numeric:tabular-nums}
td{padding:2px 16px 2px 0}`;

if (HAS_DOM && typeof customElements !== "undefined") {
  if (!customElements.get("tt-fireworks")) {
    customElements.define("tt-fireworks", class extends HTMLElement {
      connectedCallback() {
        if (this.ttCanvas) return;
        const root = this.attachShadow({ mode: "open" });
        root.innerHTML = '<style>:host{display:block;position:relative}canvas{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}</style><canvas aria-hidden="true"></canvas><slot></slot>';
        this.ttCanvas = root.querySelector("canvas");
        const when = this.getAttribute("trigger");
        if (when) trigger(this, when, () => this.launch());
      }
      /** Start a show drawn inside this element. Attributes give the defaults. */
      launch(opts = {}) {
        const step = parseStep(["fireworks", ...tokensFrom(this, true)]);
        return make("fireworks", { ...step, view: "canvas", ...opts, target: this });
      }
    });
  }

  if (!customElements.get("tt-menu")) {
    customElements.define("tt-menu", class extends HTMLElement {
      connectedCallback() {
        if (this.shadowRoot) return;
        const root = this.attachShadow({ mode: "open" });
        root.innerHTML = `<style>${MENU_CSS}</style><div class="list" part="list"></div><div class="step" part="step"></div>
<div class="readout" part="readout" aria-live="polite"></div>
<div class="controls" part="controls"><button data-a="back">Back</button><button data-a="next">Next</button><button data-a="stop">Stop</button></div>
<div class="score" part="score"></div>`;
        this.$ = (sel) => root.querySelector(sel);
        root.querySelector(".controls").addEventListener("click", (e) => this.runner?.[e.target.dataset.a]?.());
        queueMicrotask(() => Promise.all([...loading]).then(() => this.render()));
      }
      render() {
        const only = (this.getAttribute("presets") || "").split(",").map((s) => s.trim()).filter(Boolean);
        const list = this.$(".list");
        list.textContent = "";
        for (const p of presets()) {
          if (only.length && !only.includes(p.name)) continue;
          const b = document.createElement("button");
          b.textContent = p.name;
          b.title = `${p.steps} step${p.steps === 1 ? "" : "s"} · ${p.first}`;
          b.addEventListener("click", () => this.play(p.name));
          list.appendChild(b);
        }
      }
      /** Run a preset or line here, with this menu as its display. */
      play(target) {
        this.runner?.stop();
        this.$(".score").textContent = "";
        this.setAttribute("running", "");
        const r = (this.runner = run(target, { source: this, target: this.$(".readout") }));
        r.on("step", (s) => { this.$(".step").textContent = `${s.label}  ·  ${s.step}/${s.of}`; });
        r.on("ready", (s) => { this.$(".step").textContent = `next: ${s.next}`; this.$(".readout").textContent = "space or Next to start"; });
        r.on("summary", (s) => { if (s.score) this.$(".score").replaceChildren(scoreTable(s.score)); });
        r.done.catch((e) => { this.$(".step").textContent = e.message; }).finally(() => {
          if (this.runner === r) {
            this.removeAttribute("running");
            this.runner = null;
            this.$(".step").textContent = "";
            this.$(".readout").textContent = "";
          }
        });
        return r;
      }
    });
  }

  const start = () => {
    scan();
    new MutationObserver((list) => {
      for (const m of list) for (const node of m.addedNodes) if (node.nodeType === 1) scan(node);
    }).observe(document.documentElement, { childList: true, subtree: true });
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
}

function scoreTable(card) {
  const show = (t) => (t == null ? "DNF" : fmt(t, { decimals: 2 }));
  const rows = card.solves.map((s, i) => [s.label || `solve ${i + 1}`, show(s.time)]);
  rows.push(["best", show(card.best)], ["mean", show(card.mean)]);
  if ("average" in card) rows.push(["average (WCA)", show(card.average)]);
  const table = document.createElement("table");
  for (const [a, b] of rows) {
    const tr = table.insertRow();
    tr.insertCell().textContent = a;
    tr.insertCell().textContent = b;
  }
  return table;
}

const tt = {
  run, define, load, presets, make, stopwatch, timer, wait, metronome, counter, fireworks,
  plan, stream, score, parseLine, parseText, tokenize, expand, describe, scan, Rand, ParseError,
};
if (typeof globalThis !== "undefined" && !globalThis.tt) globalThis.tt = tt;
export default tt;
