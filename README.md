# Sudoku Solver — step by step

A small web app that solves a Sudoku puzzle and **explains every move**. Enter a
puzzle (or load one of the bundled examples), hit **Solve**, and watch the board
fill in while a step-by-step log describes *what* happened at each move and
*why* the solver reached for that particular technique.

The solver is deliberately not a brute-force black box. It works in two phases:

1. **Logical phase** — it runs a priority-ordered list of real Sudoku
   techniques (naked/hidden singles, subsets, pointing pairs, fish patterns,
   XY-Wing, chains, …) and keeps going until a full pass makes no progress.
2. **Search phase** — only if the puzzle is still unsolved does it fall back to
   guessing in the fewest-candidates cell and backtracking. Every guess and
   backtrack is logged with the reason, so you can see exactly where logic ran
   out.

The result of a genuinely hard puzzle is a log that reads like a human
explanation — "Hidden triple in this box…", "X-Wing on digit 7…", "Chosen
because singles, pairs and pointing pairs made no progress, so we tried
X-Wing" — rather than a wall of "Guess… / Backtrack…".

## Requirements

- **Python 3.9+** (standard library only — nothing to install)
- A web browser

## Running the web app

```bash
python server.py            # default port 8000
python server.py 9000       # or pick your own port
```

Then open <http://localhost:8000> (or the port you chose).

The server is a single-file, standard-library HTTP server. It serves the static
front-end and two JSON endpoints:

| Endpoint | Method | Description |
|---|---|---|
| `/api/solve` | `POST` | Body `{"grid": [81 ints, 0 = empty]}` → full solve result with step log |
| `/api/examples` | `GET` | The bundled example puzzles |
| `/api/random` | `GET` | A random puzzle from `sudoku.csv` (O(1) seek-based read) |
| `/api/health` | `GET` | Liveness check |

### Using the UI

- **Load an example** from the dropdown (Easy / Medium / Hard / Diabolical),
  or click **Random puzzle** to load one from `sudoku.csv` (~9 million
  puzzles). The status bar shows the clue count and a color-coded difficulty
  badge: **Easy** (≥36 clues), **Medium** (28–35), **Hard** (22–27),
  **Expert** (<22).
- Click cells and type `1`–`9` (Backspace / `0` clears a cell). A number pad
  appears under the board for click/keyboard-free entry.
- **Selecting a cell** highlights its row, column, and 3×3 box with a light
  fill so you can see the units it constrains at a glance.
- **Solve** starts the animated replay; **Stop** cancels it.
- **Step** solves the puzzle first, then advances one move at a time: each
  click applies the next step to the board and appends its explanation to the
  log. **Stop** exits step mode.
- **Pencil marks** toggles candidate display: every empty cell shows the digits
  it could still take. While replaying (Solve or Step), pencil marks track the
  solver's candidate eliminations step by step.
- When the puzzle **completes correctly**, the board celebrates: all numbers
  turn green with a brief pop animation.
- The **Speed** selector controls replay speed (Slow → Instant).
- The right-hand **Step-by-step log** lists every move with its explanation.
  Clicking a log entry highlights the cell it touched (strong ring) and every
  cell whose candidate it eliminated (lighter ring).

## Using the solver from the command line

`solver.py` is a standalone script:

```bash
python solver.py            # solve the bundled examples, print a summary
python solver.py --stats    # solve the benchmark set, print a technique-usage table
```

`--stats` reports, per benchmark puzzle, whether it solved, how many guesses
were needed, the step count, and the wall-clock time, followed by a
technique → count table across the whole set.

## Using the solver as a library

```python
import solver

result = solver.solve(grid)   # grid: list of 81 ints, 0 = empty
# result = {
#   "solved": bool,
#   "grid": [81 ints],          # solved grid
#   "initial_grid": [81 ints],  # the puzzle as given
#   "steps": [ ... ],           # one dict per move
#   "boards": [ ... ],          # board snapshot before each step
#   "cands": [ ... ],           # candidate-set snapshot before each step
# }
```

Each step dict has:

| Field | Meaning |
|---|---|
| `type` | technique name (`naked_single`, `hidden_single`, `x_wing`, `xy_wing`, `aic`, `guess`, `backtrack`, `done`, `error`, …) |
| `row`, `col`, `value` | the cell and digit placed (null for non-placement steps) |
| `eliminated` | list of `[row, col, digit]` candidates removed by this step |
| `reason` | human-readable description of what changed |
| `detail` | the **"why this method"** line — which techniques were exhausted before this one fired, or how deep the search is |

The `boards` list holds a full 81-int snapshot before every step, so a client
can single-step forward and backward: render `boards[n]` and apply `steps[n]`.
`cands` holds a matching candidate-set snapshot per step (each entry is a list
of 81 cells; empty cells list the digits still possible), which the UI uses to
animate pencil marks as eliminations happen.

## Running the tests

```bash
python test_sudoku.py
```

No dependencies. The suite checks that examples and benchmarks solve to valid
grids with preserved clues, that conflicting/unsolvable puzzles are reported,
that the board snapshots are consistent with the steps (the replay invariant),
that the diabolical benchmark solves with **zero guesses**, and that every step
carries a "why this method" explanation.

## Project layout

| File | Role |
|---|---|
| `advanced.py` | Core `Grid` model (values, candidates, inverse index), the `Log`/`Step` recording, and the `@register` technique registry |
| `techniques_basic.py` | Basic techniques: naked/hidden singles, naked & hidden pairs/triples/quadruples, pointing pairs, box-line reduction, basic coloring |
| `techniques_fish.py` | Fish patterns: X-Wing, Swordfish, Jellyfish, and X-Cycle |
| `techniques_pairs.py` | Pair-based patterns: XY-Wing (and a W-Wing stub) |
| `techniques_chains.py` | Chain-based patterns: AIC (alternating inference chain) |
| `solver.py` | The two-phase solver (logical → search), the "why this method" reasoning, examples, benchmarks, and the CLI |
| `server.py` | Standard-library web server (static files + `/api/solve`, `/api/examples`, `/api/random`) |
| `index.html` / `app.js` / `style.css` | The web front-end: board editing, number pad, pencil marks, unit highlighting, animated replay, single-step mode, solved-board celebration, step log |
| `test_sudoku.py` | Test suite |
| `sudoku.csv` | ~9 million puzzle/solution pairs (81 digits, comma, 81 digits per row) backing the **Random puzzle** button — not committed; download it separately |
| `sudoku_solver.py` | The original single-file engine (kept for reference; the app now uses `solver.py`) |

## Techniques used

Tried in priority order, lower number first:

| # | Technique | Module |
|---|---|---|
| 1 | Naked Single | `techniques_basic.py` |
| 2 | Hidden Single | `techniques_basic.py` |
| 3 | Naked Pair | `techniques_basic.py` |
| 4 | Naked Triple | `techniques_basic.py` |
| 5 | Naked Quadruple | `techniques_basic.py` |
| 6 | Hidden Pair | `techniques_basic.py` |
| 7 | Hidden Triple | `techniques_basic.py` |
| 8 | Pointing Pair | `techniques_basic.py` |
| 9 | Box-Line Reduction | `techniques_basic.py` |
| 10 | Coloring (Basic) | `techniques_basic.py` |
| 11 | X-Wing | `techniques_fish.py` |
| 12 | Swordfish | `techniques_fish.py` |
| 13 | Jellyfish | `techniques_fish.py` |
| 14 | X-Cycle | `techniques_fish.py` |
| 15 | XY-Wing | `techniques_pairs.py` |
| 16 | W-Wing | `techniques_pairs.py` |
| 17 | AIC (Alternating Inference Chain) | `techniques_chains.py` |

If no technique can make progress, the solver moves to the search phase
(guessing + backtracking) and says so in the log.

## How it works

- **`Grid`** (`advanced.py`) tracks each cell's value, its candidate set, and an
  inverse index (digit → cells that can take it). Placing a value or eliminating
  a candidate keeps all three in sync; eliminating the last-but-one candidate
  auto-places a naked single.
- **Techniques** are plain functions `fn(grid, log) -> bool` registered with
  `@register(name, priority)`. Each one looks for its pattern, records any
  placements/eliminations in the `Log` with a human-readable reason, and returns
  `True` if it made progress.
- **`solver.solve`** loops: run a full pass over the techniques in priority
  order (restarting from the top whenever one fires) until a pass is a no-op.
  If the puzzle is still unsolved it guesses in the fewest-candidates cell,
  re-runs the logical phase on the branch, and backtracks on contradiction.
  Each recorded step gets a `detail` line explaining why that technique was the
  one that fired at that point.

## Notes & known limitations

- **`sudoku.csv`** (not committed — ~1.4 GB) is required for the **Random
  puzzle** button. Each row is `puzzle,solution` (81 digits each). The server
  reads it with a direct byte seek, so loading a random puzzle is O(1) no
  matter how large the file is. Without the file the button reports an error
  but everything else works.
- The bundled **Diabolical (28-clue)** benchmark solves with **zero guesses** —
  pure logic, including XY-Wing and AIC.
- A couple of the harder benchmarks (2.6, 7.2) can hit a dead end in the logical
  phase when an advanced technique over-eliminates; the solver then falls back
  to a clean guess-and-backtrack search from the original grid, so they still
  solve correctly (just with guesses). The log records this transition.
- `sudoku_solver.py` is the original, simpler engine kept for reference. The
  app and tests use the new `solver.py` engine.
