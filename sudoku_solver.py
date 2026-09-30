"""Sudoku solver that records a human-readable explanation for every step.

The solver works in passes:
  1. Naked singles  - a cell whose candidates have been reduced to one.
  2. Hidden singles - a digit that fits in only one cell of a row/col/box.
  3. Backtracking   - when no logical technique applies, make a reasoned guess
                      (fewest-candidates cell) and undo it if it fails.

Every placement, guess and backtrack is appended to a list of step dicts so
the UI can replay and explain the whole solution.
"""

# Each puzzle below was generated and verified to have exactly one solution.
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
]


def _unit_cells(kind, idx):
    if kind == "row":
        return [(idx, c) for c in range(9)]
    if kind == "col":
        return [(r, idx) for r in range(9)]
    br, bc = 3 * (idx // 3), 3 * (idx % 3)
    return [(br + i, bc + j) for i in range(3) for j in range(3)]


def _all_units():
    units = [("row", i) for i in range(9)]
    units += [("col", i) for i in range(9)]
    units += [("box", i) for i in range(9)]
    return units


def _unit_label(kind, idx):
    names = {"row": "Row", "col": "Column", "box": "Box"}
    return f"{names[kind]} {idx + 1}"


def candidates(grid, r, c):
    """Digits that may legally go in cell (r, c)."""
    used = set()
    for i in range(9):
        used.add(grid[r * 9 + i])
        used.add(grid[i * 9 + c])
    br, bc = 3 * (r // 3), 3 * (c // 3)
    for i in range(br, br + 3):
        for j in range(bc, bc + 3):
            used.add(grid[i * 9 + j])
    return [d for d in range(1, 10) if d not in used]


def validate(grid):
    """Return a list of human-readable conflicts among the given clues."""
    errors = []
    for kind, idx in _all_units():
        seen = {}
        label = _unit_label(kind, idx)
        for (r, c) in _unit_cells(kind, idx):
            v = grid[r * 9 + c]
            if not v:
                continue
            if v in seen:
                pr, pc = seen[v]
                errors.append(
                    f"{label} contains two {v}s — at R{pr + 1}C{pc + 1} and "
                    f"R{r + 1}C{c + 1}. The clues conflict, so the puzzle has no solution."
                )
            else:
                seen[v] = (r, c)
    return errors


def _naked_single_step(grid, r, c, v):
    row_excl = sorted({grid[r * 9 + i] for i in range(9) if grid[r * 9 + i] and i != c})
    col_excl = sorted({grid[i * 9 + c] for i in range(9) if grid[i * 9 + c] and i != r})
    br, bc = 3 * (r // 3), 3 * (c // 3)
    box_excl = sorted(
        {grid[i * 9 + j] for i in range(br, br + 3) for j in range(bc, bc + 3)
         if grid[i * 9 + j] and (i, j) != (r, c)}
    )

    def fmt(xs):
        return ", ".join(map(str, xs)) if xs else "nothing"

    reason = (
        f"Naked single — cell R{r + 1}C{c + 1} must be {v}. The row already has "
        f"{fmt(row_excl)}, the column has {fmt(col_excl)} and the 3×3 box has "
        f"{fmt(box_excl)}, which together rule out every other digit."
    )
    return {"type": "naked_single", "row": r, "col": c, "value": v, "reason": reason}


def _hidden_single_step(kind, idx, r, c, d):
    label = _unit_label(kind, idx).lower()
    reason = (
        f"Hidden single — in {label}, the digit {d} fits in exactly one cell: "
        f"R{r + 1}C{c + 1}. Every other empty cell in that {kind} is blocked by a "
        f"{d} sitting elsewhere in its row, column or box."
    )
    return {"type": "hidden_single", "row": r, "col": c, "value": d, "reason": reason}


def _guess_step(r, c, v, cands):
    reason = (
        f"Guess — no logical technique applies anymore. Cell R{r + 1}C{c + 1} has the "
        f"fewest remaining options ({', '.join(map(str, cands))}), so we try {v}. If it "
        f"leads to a contradiction, the solver will backtrack and try another."
    )
    return {"type": "guess", "row": r, "col": c, "value": v,
            "candidates": list(cands), "reason": reason}


def _backtrack_step(r, c, v):
    reason = (
        f"Backtrack — the guess of {v} at R{r + 1}C{c + 1} led to a contradiction, so it "
        f"is removed and the next candidate for that cell will be tried."
    )
    return {"type": "backtrack", "row": r, "col": c, "value": v, "reason": reason}


def _solve(grid, steps):
    """Fill `grid` in place. Returns True when solved; appends steps as it goes."""
    while True:
        # Pass 1: naked singles (rescan until stable, since each placement opens new ones)
        progress = False
        for r in range(9):
            for c in range(9):
                if grid[r * 9 + c] == 0:
                    cands = candidates(grid, r, c)
                    if not cands:
                        return False  # contradiction -> caller backtracks
                    if len(cands) == 1:
                        grid[r * 9 + c] = cands[0]
                        steps.append(_naked_single_step(grid, r, c, cands[0]))
                        progress = True
        if progress:
            continue

        # Pass 2: hidden singles across every row, column and box
        placed = False
        for kind, idx in _all_units():
            cells = _unit_cells(kind, idx)
            for d in range(1, 10):
                if any(grid[r * 9 + c] == d for r, c in cells):
                    continue  # digit already placed in this unit
                spots = [(r, c) for r, c in cells
                         if grid[r * 9 + c] == 0 and d in candidates(grid, r, c)]
                if len(spots) == 1:
                    r, c = spots[0]
                    grid[r * 9 + c] = d
                    steps.append(_hidden_single_step(kind, idx, r, c, d))
                    placed = True
        if placed:
            continue

        # Pass 3: no logical move left -> reasoned guess (fewest candidates first).
        # Each guess is tried on a *copy* of the grid: if it fails, every
        # placement made along that branch (including logical ones) is discarded.
        empties = [(r, c) for r in range(9) for c in range(9) if grid[r * 9 + c] == 0]
        if not empties:
            return True
        r, c = min(empties, key=lambda rc: len(candidates(grid, *rc)))
        cands = candidates(grid, r, c)
        if not cands:
            return False
        for v in cands:
            sub = list(grid)
            sub[r * 9 + c] = v
            steps.append(_guess_step(r, c, v, cands))
            if _solve(sub, steps):
                grid[:] = sub  # copy the solved branch back up
                return True
            steps.append(_backtrack_step(r, c, v))
        return False


def solve(grid):
    """Solve a puzzle given as 81 ints (0 = empty). Returns dict with
    {solved, grid, steps} where each step has type/row/col/value/reason."""
    steps = []
    errors = validate(grid)
    if errors:
        for e in errors:
            steps.append({"type": "error", "row": None, "col": None,
                          "value": None, "reason": e})
        steps.append({"type": "error", "row": None, "col": None, "value": None,
                      "reason": "The puzzle cannot be solved because the given clues conflict."})
        return {"solved": False, "grid": list(grid), "steps": steps}

    work = list(grid)
    ok = _solve(work, steps)
    logical = sum(1 for s in steps if s["type"] in ("naked_single", "hidden_single"))
    guesses = sum(1 for s in steps if s["type"] == "guess")
    backtracks = sum(1 for s in steps if s["type"] == "backtrack")
    if ok:
        steps.append({
            "type": "done", "row": None, "col": None, "value": None,
            "reason": (f"Solved! The search made {logical} logical placement(s), "
                       f"{guesses} guess(es) and {backtracks} backtrack(s). "
                       f"Total steps: {len(steps) - 1}."),
        })
        return {"solved": True, "grid": work, "steps": steps}

    steps.append({"type": "error", "row": None, "col": None, "value": None,
                  "reason": ("No solution exists: every possible line of reasoning was "
                             "explored and each one led to a contradiction.")})
    return {"solved": False, "grid": list(grid), "steps": steps}


if __name__ == "__main__":
    for ex in EXAMPLES:
        res = solve(ex["grid"])
        kinds = {}
        for s in res["steps"]:
            kinds[s["type"]] = kinds.get(s["type"], 0) + 1
        print(f"{ex['name']}: solved={res['solved']} steps={kinds}")
