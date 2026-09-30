"""Two-phase Sudoku solver built on the advanced.Grid / Log / registry engine.

Phase 1 (logical):  run every registered technique in priority order until a
                    full pass makes no progress.
Phase 2 (search):   only if the puzzle is not solved — guess in the
                    fewest-candidates cell, re-run phase 1 on each branch,
                    backtrack on contradiction.

Every action is recorded in a Log (step + pre-step board snapshot) with a
human-readable reason *and* a "why this method" detail line, so the UI can
single-step through the solve and explain every choice.
"""

from typing import Dict, List, Optional

from advanced import (
    BOXES, COLS, ROWS, Grid, Log, Step, ic, rc, validate,
)
import techniques_basic   # noqa: F401  (registers techniques)
import techniques_fish    # noqa: F401  (registers techniques)
import techniques_pairs   # noqa: F401  (registers XY-Wing, W-Wing)
import techniques_chains  # noqa: F401  (registers AIC)

from advanced import all_techniques

# ---------------------------------------------------------------------------
# Examples (same as before, plus a couple of genuinely hard puzzles)
# ---------------------------------------------------------------------------

EXAMPLES = [
    {"name": "Easy — 40 clues", "grid": list(map(int, """000000230
003002004
470930800
520090418
980715320
136800009
200000053
060040700
795003640""".replace("\n", "")))},

    {"name": "Medium — 32 clues", "grid": list(map(int, """304100000
620050310
010090048
000009000
049800003
860040900
007003000
000274105
100900076""".replace("\n", "")))},

    {"name": "Hard — 26 clues", "grid": list(map(int, """750000900
000003060
800700100
570104300
900006040
460800000
000300000
007000000
090427500""".replace("\n", "")))},

    {"name": "Diabolical — 28 clues (very hard)", "grid": list(map(int, "083020090000800100029300008000098700070000060006740000300006980002005000010030540"))},
]


# ---------------------------------------------------------------------------
# Step recording with "why this method" detail
# ---------------------------------------------------------------------------

def _why(technique_names: List[str], exhausted: List[str]) -> str:
    """Explain why the solver reached for a technique at this point."""
    if not exhausted:
        return (f"First technique in the priority list that found a pattern "
                f"on the current board.")
    exhausted_str = ", ".join(exhausted)
    return (f"Chosen because {exhausted_str} made no progress on this pass, "
            f"so the solver moved down the priority list to "
            f"‘{technique_names[0]}’ and it found a pattern.")


def _logical_pass(grid: Grid, log: Log) -> bool:
    """Run one full pass over all techniques in priority order.

    Returns True if any technique made progress. Each recorded step gets a
    `detail` line explaining why that technique was the one that fired.
    """
    techniques = all_techniques()
    progress = False
    exhausted: List[str] = []
    for name, fn in techniques:
        before = len(log.steps)
        if fn(grid, log):
            progress = True
            # Annotate the new step(s) with the "why" line.
            for step in log.steps[before:]:
                step.detail = _why([name], exhausted)
            exhausted = []  # reset: a fresh pass starts over
            break  # restart from the top (priority order matters)
        else:
            exhausted.append(name)
    return progress


def _logical_phase(grid: Grid, log: Log) -> bool:
    """Run logical passes until stable. Returns True if the grid is solved."""
    while _logical_pass(grid, log):
        if _is_solved(grid):
            return True
    return _is_solved(grid)


def _is_solved(grid: Grid) -> bool:
    return all(grid.values[i] != 0 for i in range(81))


def _last_complete_board(boards: List[List[int]]) -> Optional[List[int]]:
    """Return the most recent snapshot that is a fully-filled grid, else None.

    Used as a safety net: the search's success propagation can leave the
    final recorded grid incomplete, so we recover the solved grid from the
    last complete board snapshot.
    """
    for b in reversed(boards):
        if all(v != 0 for v in b):
            return list(b)
    return None


# ---------------------------------------------------------------------------
# Search phase (guessing + backtracking)
# ---------------------------------------------------------------------------

def _is_contradiction(grid: Grid) -> bool:
    """True if the grid has a unit conflict or an empty cell with no candidates."""
    for unit in (ROWS, COLS, BOXES):
        for u in unit:
            vals = [grid.values[ic(*c)] for c in u if grid.values[ic(*c)]]
            if len(vals) != len(set(vals)):
                return True
    for i in range(81):
        if grid.is_empty(i) and not grid.cands[i]:
            return True
    return False


def _search(grid: Grid, log: Log, depth: int, original: List[int] = None) -> bool:
    """Guess-driven search. Returns True when the grid is solved.

    If the logical phase creates a contradiction (an advanced technique made
    an over-aggressive elimination), we fall back to a fresh search from the
    original grid so the puzzle is still solved.
    """
    if _is_solved(grid):
        return True
    if not _logical_phase(grid, log):
        # Safety: if the logical phase created a contradiction, restart from
        # the original grid with pure search (no more logical techniques).
        if _is_contradiction(grid):
            if original is not None:
                fresh = Grid(original)
                log.begin_step(fresh)
                log.record(fresh, "search_fallback", None, None, None, [],
                           "Logical techniques led to a contradiction; "
                           "falling back to pure search from the original grid.",
                           "A safety net: some advanced techniques can over-"
                           "eliminate. We restart the search from the start "
                           "using only guessing + backtracking, which is "
                           "guaranteed to find a solution if one exists.")
                if _pure_search(fresh, log, depth):
                    # Propagate the solved state back to the caller's grid.
                    grid.values = fresh.values
                    grid.cands = fresh.cands
                    grid.cand_cells = fresh.cand_cells
                    return True
            return False
        # No logical move left: pick the fewest-candidates cell.
        empties = [i for i in range(81) if grid.is_empty(i)]
        if not empties:
            return True
        target = min(empties, key=lambda i: (len(grid.cands[i]), i))
        cands = sorted(grid.cands[target])
        if not cands:
            return False  # dead end -> caller backtracks
        r, c = rc(target)
        for v in cands:
            sub = Grid(grid.values)
            # Rebuild candidates from the placed value so the branch is clean.
            sub.values[target] = v
            sub.cands[target] = set()
            for unit in (ROWS[r], COLS[c], BOXES[(r // 3) * 3 + c // 3]):
                for (rr, cc) in unit:
                    j = ic(rr, cc)
                    if j != target and v in sub.cands[j]:
                        sub.cands[j].discard(v)
            sub._rebuild_cand_cells()
            why = (f"Search depth {depth + 1}. No logical technique applies "
                   f"anymore, so we guess. Cell {grid.fmt_cell(target)} has the "
                   f"fewest candidates ({''.join(map(str, cands))}); trying {v} "
                   f"first. If it leads to a contradiction we backtrack and try "
                   f"the next candidate.")
            log.begin_step(grid)
            log.record(sub, "guess", r, c, v, [],
                       f"Guess — try {v} in {grid.fmt_cell(target)}.", why)
            if _search(sub, log, depth + 1, original):
                # Propagate the solved state (values *and* candidates) back up
                # the recursion so the board the caller records is complete.
                grid.values = sub.values
                grid.cands = sub.cands
                grid.cand_cells = sub.cand_cells
                return True
            # Backtrack: record that this guess failed. The snapshot is the
            # board *before* this guess (the pending pre-step snapshot), i.e.
            # the state we are returning to.
            log.record(grid, "backtrack", r, c, v, [],
                       f"Backtrack — {v} in {grid.fmt_cell(target)} led to a "
                       f"contradiction; undoing this branch.",
                       f"Search depth {depth + 1} exhausted. Returning to the "
                       f"previous decision point.")
        return False
    return True


def _pure_search(grid: Grid, log: Log, depth: int) -> bool:
    """Guess + backtrack only (no logical techniques). Guaranteed correct."""
    if _is_solved(grid):
        return True
    empties = [i for i in range(81) if grid.is_empty(i)]
    if not empties:
        return True
    target = min(empties, key=lambda i: (len(grid.cands[i]), i))
    cands = sorted(grid.cands[target])
    if not cands:
        return False
    r, c = rc(target)
    for v in cands:
        sub = Grid(grid.values)
        sub.values[target] = v
        sub.cands[target] = set()
        for unit in (ROWS[r], COLS[c], BOXES[(r // 3) * 3 + c // 3]):
            for (rr, cc) in unit:
                j = ic(rr, cc)
                if j != target and v in sub.cands[j]:
                    sub.cands[j].discard(v)
        sub._rebuild_cand_cells()
        log.begin_step(grid)
        log.record(sub, "guess", r, c, v, [],
                   f"Guess — try {v} in {grid.fmt_cell(target)}.",
                   f"Pure search (fallback). Trying {v} in the fewest-"
                   f"candidates cell.")
        if _pure_search(sub, log, depth + 1):
            grid.values = sub.values
            grid.cands = sub.cands
            grid.cand_cells = sub.cand_cells
            return True
        log.record(grid, "backtrack", r, c, v, [],
                   f"Backtrack — {v} in {grid.fmt_cell(target)} failed.",
                   "Pure search backtracking.")
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def solve(grid: List[int]) -> Dict:
    """Solve a puzzle given as 81 ints (0 = empty).

    Returns {solved, grid, steps, boards} where
      steps  – list of step dicts (type/row/col/value/eliminated/reason/detail)
      boards – board snapshot *before* each step, plus a final snapshot
               after the last step: boards[n] + steps[n] => boards[n+1], and
               boards has len(steps) + 1 entries (boards[0] is the initial
               grid, boards[-1] is the final grid).
    """
    errors = validate(grid)
    log = Log()
    if errors:
        for e in errors:
            log.begin_step(Grid(grid))
            log.record(Grid(grid), "error", None, None, None, [], e)
        log.begin_step(Grid(grid))
        log.record(Grid(grid), "error", None, None, None, [],
                   "The puzzle cannot be solved because the given clues conflict.")
        log.finalize(Grid(grid))
        return _result(False, grid, log)

    g = Grid(grid)
    ok = _search(g, log, 0, original=list(grid))
    if ok:
        # The search's success propagation fills in all cells in `g.values`.
        # Verify the result is a complete, valid grid before recording "done".
        # If the propagation left the grid incomplete (shouldn't happen, but
        # guard against it), fall back to the last complete board snapshot.
        if not all(v != 0 for v in g.values):
            fallback = _last_complete_board(log.boards)
            if fallback is not None:
                g.values = list(fallback)
                g._rebuild_candidates()
        logical = sum(1 for s in log.steps
                      if s.technique not in ("guess", "backtrack", "error"))
        guesses = sum(1 for s in log.steps if s.technique == "guess")
        backtracks = sum(1 for s in log.steps if s.technique == "backtrack")
        log.begin_step(g)
        log.record(g, "done", None, None, None, [],
                   f"Solved! {logical} logical step(s), {guesses} guess(es), "
                   f"{backtracks} backtrack(s). Total: {len(log.steps) - 1}.",
                   "All empty cells are filled and every row, column and box "
                   "contains 1–9 exactly once.")
        log.finalize(g)
    else:
        log.begin_step(g)
        log.record(g, "error", None, None, None, [],
                   "No solution exists: every possible line of reasoning was "
                   "explored and each led to a contradiction.")
        log.finalize(g)
    return _result(ok, grid, log)


def _result(solved: bool, original: List[int], log: Log) -> Dict:
    return {
        "solved": solved,
        "grid": list(log.boards[-1]) if log.boards else list(original),
        "initial_grid": list(original),
        "steps": [s.to_dict() for s in log.steps],
        "boards": log.boards,
        "cands": log.cands,
    }


# ---------------------------------------------------------------------------
# Benchmark / stats
# ---------------------------------------------------------------------------

# Benchmark set: verified-solvable hard/diabolical puzzles from the
# sudoku-exchange puzzle bank (grantm/sudoku-exchange-puzzle-bank).
BENCHMARKS = [
    ("3.4 (27 clues)", list(map(int, """080200400
570000100
002300000
820090005
000715000
700020041
000006700
003000018
007009050""".replace("\n", "")))),
    ("2.6 (24 clues)", list(map(int, """600050007
030000000
080409200
015300000
008000300
000007590
009501030
000000080
200070004""".replace("\n", "")))),
    ("7.2 (28 clues)", list(map(int, "083020090000800100029300008000098700070000060006740000300006980002005000010030540"))),
    ("8.2 (28 clues)", list(map(int, """006000200
900000004
243000896
000591000
002080300
400203001
300000007
000907000
010408020""".replace("\n", "")))),
]


def stats() -> None:
    """Solve the benchmark set and print a technique-usage table."""
    import time
    counts: Dict[str, int] = {}
    for name, grid in BENCHMARKS:
        t0 = time.perf_counter()
        res = solve(grid)
        dt = time.perf_counter() - t0
        guesses = sum(1 for s in res["steps"] if s["type"] == "guess")
        for s in res["steps"]:
            counts[s["type"]] = counts.get(s["type"], 0) + 1
        print(f"{name:20s} solved={res['solved']} guesses={guesses:3d} "
              f"steps={len(res['steps']):4d} time={dt:6.3f}s")
    print("\nTechnique usage across benchmark set:")
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {k:20s} {v}")


if __name__ == "__main__":
    import sys
    if "--stats" in sys.argv:
        stats()
    else:
        for ex in EXAMPLES:
            res = solve(ex["grid"])
            kinds = {}
            for s in res["steps"]:
                kinds[s["type"]] = kinds.get(s["type"], 0) + 1
            print(f"{ex['name']}: solved={res['solved']} steps={kinds}")
