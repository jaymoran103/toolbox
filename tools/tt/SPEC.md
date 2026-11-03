# timetools spec

One syntax drives the CLI (`py/`) and the browser kit (`web/timetools.js`).
A line pasted from one runs in the other. `spec/cases.json` holds the cases
both test suites run, so a gap between them fails a test.

## Lines

A line is one tool run: a tool, its positional values, then options.

```text
metronome 96 --for 4m -b 3 --label "Verse"
```

- A leading `tt` is optional. Short names work: `sw`, `t`, `m`, `c`, `fw`.
- `--name value` and `--name=value` are the same. A flag is `--name` or `--no-name`.
- Quotes group words. `'single'` is literal. `"double"` takes `\"` and `\\`.
- `;` separates steps on one line.
- `#` starts a comment at the start of a line, or when a space follows it,
  so `#ff3366` stays a value.

## Values

| Kind | Examples |
| --- | --- |
| Duration | `90`, `90s`, `5m`, `1h30m`, `2.5m`, `1:30`, `1:02:03` |
| Range | `20-40`, `30s-1m`, `1-2m`. One value is picked per run. The high end's unit carries to a bare low end. |
| Rate | `2`, `2/s`, `30/m`, `4-8/h`. Per second when bare. |
| Endless | `forever`, for a fireworks span and for `--for` |

## Tools

| Tool | Positional | Options |
| --- | --- | --- |
| `stopwatch` | — | `--for`, `--cap` (past it the solve is DNF), `--solve` (space or enter submits) |
| `timer` | duration, label | `--rings`, `--sound` |
| `wait` | duration | — |
| `metronome` | bpm (20 to 400) | `-b/--beats`, `--for`, `--sound` |
| `counter` | label | `--start`, `--step` |
| `fireworks` | span | `-n/--count` or `-r/--rate`, `--spread random\|even`, `--seed`, `--cluster`, `--within`, `--sound`, and styling |

Every tool takes `--label`. Fireworks styling: `--palette festival|ember|frost|gold`,
then `--colors`, `--children`, `--trail`, `--length`, `--size`, `--gravity`,
`--crackle`, `--rocket`. A single flag overrides the palette.

Sound is on for `timer` and `metronome` and off for `fireworks`.

Some options belong to one side. The other side accepts and ignores them.

| Side | Options |
| --- | --- |
| CLI | `--view plain\|big\|none` |
| Web | `--view none\|text\|canvas`, `--target`, `--trigger click\|load\|visible`, `--origin element\|random` |

## Presets

A preset is a named block of lines. `@` lines set how the block runs.

```text
[gauntlet]
@repeat 5
@advance key
@score wca
timer 15s --label "Inspect {n}"
stopwatch --solve --cap 2m --label "Solve {n}"
```

| Directive | Meaning |
| --- | --- |
| `@repeat N` | Play the block N times. `{n}` in a label is the round. |
| `@gap DUR` | A `wait` before each step after the first |
| `@advance auto\|key` | Move on alone, or wait for space or enter |
| `@score times\|wca` | Scorecard of the stopwatch steps: each time, best, mean, and with `wca` the average with best and worst dropped. Two DNFs make it DNF. |

Lines before any `[name]` form an unnamed block.

## Keys

The same keys work in the terminal and, during a run, on the page.

| Key | Does |
| --- | --- |
| space | pause or resume; in a solve or a wait, submit or skip |
| enter | lap; in a solve or a wait, submit or skip |
| `n`, `b` | next step, back one step |
| `q`, esc | quit the run |
| ↑ ↓ → ← `t` | metronome: ±1, ±5, tap tempo |
| space enter ↑ ↓ `u` `r` | counter: add, add, add, subtract, undo, reset |

## Results and events

Each step gives a result: `tool`, `label`, `outcome` (`done`, `stopped`,
`cancelled`, `skipped`, `dnf`), `nav` (`next`, `back`, `quit` or empty),
`elapsed`, and the tool's own fields (`laps`, `bpm`, `beats`, `n`, `fired`,
`count`, `total`).

Events: `start`, `burst`, `beat`, `lap`, `change`, `pause`, `done` from tools.
A run adds `step`, `ready` (waiting for a key) and `summary` (results and
score). The CLI writes them with `--emit FILE|-` and runs `--on EVENT=CMD`.
The browser dispatches them as `tt:<event>` DOM events.

## Randomness

Fireworks use seeded mulberry32 in both languages. A seed gives the same
burst times, and the same rocket and spark layout, in the terminal and the
browser. Random gaps in a `forever` show are uniform up to twice the mean.
