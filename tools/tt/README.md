# timetools

Time tools for the terminal and the browser: stopwatch, timer, metronome,
counter and fireworks. Both speak one line syntax, so a preset written for
one runs in the other. [SPEC.md](SPEC.md) has the full syntax.

## Terminal

Needs only Python 3.9 or newer, on macOS or Linux.

```sh
git clone https://github.com/jaymoran103/timetools && cd timetools && ./install.sh
```

```sh
tt                                      # menu of presets and tools
tt metronome 96 --for 4m -b 3           # one run; `metronome ...` works too
tt timer 25m focus --view big           # full-screen view
tt run gauntlet                         # a preset
tt run "metronome 92 --for 3m; wait 15s; metronome 120 --for 4m"
tt presets                              # list presets
tt help fireworks
```

Presets live in `~/.config/timetools/*.tt` and `./*.tt`.
[presets/examples.tt](presets/examples.tt) has a setlist, a cube gauntlet
and a game-night fireworks loop.

Hand events to other programs with `--emit -` (JSON lines on stdout),
`--emit FILE`, or `--on done='notify-send done'`. `--out runs.json` saves
the results and scorecard.

## Browser

`web/timetools.js` is one ES module with no dependencies.

```html
<script type="module" src="timetools.js"></script>
<script type="text/tt" src="presets.tt"></script>

<tt-menu></tt-menu>
<button data-tt-run="setlist">Play the set</button>
<button data-tt-run="fireworks 5s -r 2-4/s">Celebrate</button>
<button data-tt="timer" data-tt-duration="5m" data-tt-target="#out">Start</button>
```

```js
import tt from "./timetools.js";
const run = tt.run("gauntlet");
run.on("summary", ({ score }) => console.log(score.average));
tt.fireworks({ span: "10s", count: "20-30" }).on("burst", () => card.classList.add("pop"));
```

Open [web/demo.html](web/demo.html) to try it.

## Tests

```sh
cd py && python3 -m unittest discover -s tests
node --test web/test.mjs
```
