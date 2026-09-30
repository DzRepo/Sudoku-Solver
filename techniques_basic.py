"""Basic (level 1-2) Sudoku techniques.

Every function follows the contract:

    def technique(grid: Grid, log: Log) -> bool

Return True when at least one candidate was eliminated or a value placed
(reasoning recorded in ``log``), else False.

Techniques implemented here:
    naked_single, hidden_single, naked_pair, naked_triple,
    naked_quadruple, hidden_pair, hidden_triple, pointing_pairs,
    box_line_reduction, color_basics (single-digit coloring eliminations)
"""

from typing import List, Set, Tuple

from advanced import (
    BOXES, COLS, ROWS, Grid, Log, Unit, ic, rc, register, units_of,
)


# ---------------------------------------------------------------------------
# Singles
# ---------------------------------------------------------------------------

@register("Naked Single", 1)
def naked_single(grid: Grid, log: Log) -> bool:
    for i in range(81):
        if grid.is_empty(i) and len(grid.cands[i]) == 1:
            d = next(iter(grid.cands[i]))
            r, c = rc(i)
            log.begin_step(grid)
            grid.place(i, d)
            log.record(grid, "naked_single", r, c, d, [],
                       f"Naked single — {grid.fmt_cell(i)} has only one candidate "
                       f"({d}), so it must be {d}.")
            return True
    return False


@register("Hidden Single", 2)
def hidden_single(grid: Grid, log: Log) -> bool:
    for d in range(1, 10):
        cells = grid.cells_with(d)
        if not cells:
            continue
        for unit in (ROWS, COLS, BOXES):
            for u in unit:
                u_ids = {ic(*cell) for cell in u}
                spots = [i for i in cells if i in u_ids and grid.is_empty(i)]
                if len(spots) == 1:
                    i = spots[0]
                    r, c = rc(i)
                    log.begin_step(grid)
                    grid.place(i, d)
                    unit_name = "row" if unit is ROWS else "column" if unit is COLS else "box"
                    log.record(grid, "hidden_single", r, c, d, [],
                               f"Hidden single — in this {unit_name}, digit {d} fits in "
                               f"exactly one cell: {grid.fmt_cell(i)}.")
                    return True
    return False


# ---------------------------------------------------------------------------
# Naked subsets
# ---------------------------------------------------------------------------

def _naked_subset(grid: Grid, log: Log, size: int, name: str) -> bool:
    """Find `size` cells in a unit sharing exactly `size` candidates."""
    for unit in (ROWS, COLS, BOXES):
        for u in unit:
            u_ids = [ic(*cell) for cell in u]
            empties = [i for i in u_ids if grid.is_empty(i)]
            if len(empties) < size:
                continue
            # group cells by candidate set
            by_cands: dict = {}
            for i in empties:
                key = frozenset(grid.cands[i])
                if len(key) == size:
                    by_cands.setdefault(key, []).append(i)
            for cset, cells in by_cands.items():
                if len(cells) >= size:
                    # pick `size` of them
                    chosen = cells[:size]
                    log.begin_step(grid)
                    removed = []
                    for i in empties:
                        if i in chosen:
                            continue
                        for d in cset & grid.cands[i]:
                            if grid.eliminate(i, d):
                                removed.append((rc(i)[0], rc(i)[1], d))
                    if removed:
                        unit_name = "row" if unit is ROWS else "column" if unit is COLS else "box"
                        cells_str = ", ".join(grid.fmt_cell(i) for i in chosen)
                        log.record(grid, "naked_subset", None, None, None, removed,
                                   f"Naked {name} — {cells_str} in this {unit_name} share "
                                   f"exactly the candidates {''.join(map(str, sorted(cset)))}, "
                                   f"so those digits are removed from the other cells of the unit.")
                        return True
                    log.discard_step()
    return False


@register("Naked Pair", 3)
def naked_pair(grid, log):
    return _naked_subset(grid, log, 2, "pair")


@register("Naked Triple", 4)
def naked_triple(grid, log):
    return _naked_subset(grid, log, 3, "triple")


@register("Naked Quadruple", 5)
def naked_quadruple(grid, log):
    return _naked_subset(grid, log, 4, "quadruple")


# ---------------------------------------------------------------------------
# Hidden subsets
# ---------------------------------------------------------------------------

def _hidden_subset(grid: Grid, log: Log, size: int, name: str) -> bool:
    """Find `size` digits in a unit that can only go in `size` cells."""
    for unit in (ROWS, COLS, BOXES):
        for u in unit:
            u_ids = {ic(*cell) for cell in u}
            for d in range(1, 10):
                # build map digit -> cells
                digit_cells = {}
                for i in u_ids:
                    if grid.is_empty(i) and d in grid.cands[i]:
                        pass
                # find all digits whose cells are within a common small set
                # simpler: for each combination of `size` digits, check
                from itertools import combinations
                for dset in combinations(range(1, 10), size):
                    cells_union = set()
                    ok = True
                    for dd in dset:
                        cells = [i for i in u_ids if grid.is_empty(i) and dd in grid.cands[i]]
                        if not cells:
                            ok = False
                            break
                        cells_union |= set(cells)
                    if ok and len(cells_union) == size:
                        # eliminate all digits in dset from other cells in unit
                        log.begin_step(grid)
                        removed = []
                        for i in u_ids:
                            if i in cells_union or not grid.is_empty(i):
                                continue
                            for dd in dset:
                                if grid.eliminate(i, dd):
                                    removed.append((rc(i)[0], rc(i)[1], dd))
                        if removed:
                            unit_name = "row" if unit is ROWS else "column" if unit is COLS else "box"
                            cells_str = ", ".join(grid.fmt_cell(i) for i in sorted(cells_union))
                            log.record(grid, "hidden_subset", None, None, None, removed,
                                       f"Hidden {name} — in this {unit_name}, digits "
                                       f"{''.join(map(str, sorted(dset)))} can only go in "
                                       f"{cells_str}, so they are removed from the other cells.")
                            return True
                        log.discard_step()
    return False


@register("Hidden Pair", 6)
def hidden_pair(grid, log):
    return _hidden_subset(grid, log, 2, "pair")


@register("Hidden Triple", 7)
def hidden_triple(grid, log):
    return _hidden_subset(grid, log, 3, "triple")


# ---------------------------------------------------------------------------
# Pointing / box-line reduction
# ---------------------------------------------------------------------------

@register("Pointing Pair", 8)
def pointing_pairs(grid: Grid, log: Log) -> bool:
    """If all candidates of digit d in a box lie in one row/col, remove d
    from that row/col outside the box."""
    for d in range(1, 10):
        for b in BOXES:
            b_ids = {ic(*cell) for cell in b}
            spots = [i for i in b_ids if grid.is_empty(i) and d in grid.cands[i]]
            if not (1 <= len(spots) <= 3):
                continue
            rows = {rc(i)[0] for i in spots}
            cols = {rc(i)[1] for i in spots}
            if len(rows) == 1:
                r = next(iter(rows))
                log.begin_step(grid)
                removed = []
                for c in range(9):
                    i = ic(r, c)
                    if i not in b_ids and grid.is_empty(i) and d in grid.cands[i]:
                        if grid.eliminate(i, d):
                            removed.append((r, c, d))
                if removed:
                    log.record(grid, "pointing_pair", None, None, None, removed,
                               f"Pointing pair — in this box, digit {d} can only go in row "
                               f"{r+1}, so {d} is removed from row {r+1} outside the box.")
                    return True
                log.discard_step()
            if len(cols) == 1:
                c = next(iter(cols))
                log.begin_step(grid)
                removed = []
                for r in range(9):
                    i = ic(r, c)
                    if i not in b_ids and grid.is_empty(i) and d in grid.cands[i]:
                        if grid.eliminate(i, d):
                            removed.append((r, c, d))
                if removed:
                    log.record(grid, "pointing_pair", None, None, None, removed,
                               f"Pointing pair — in this box, digit {d} can only go in column "
                               f"{c+1}, so {d} is removed from column {c+1} outside the box.")
                    return True
                log.discard_step()
    return False


@register("Box-Line Reduction", 9)
def box_line_reduction(grid: Grid, log: Log) -> bool:
    """If all candidates of digit d in a row/col lie in one box, remove d
    from that box outside the row/col."""
    for d in range(1, 10):
        for u, kind in ((ROWS, "row"), (COLS, "column")):
            for idx, unit in enumerate(u):
                u_ids = {ic(*cell) for cell in unit}
                spots = [i for i in u_ids if grid.is_empty(i) and d in grid.cands[i]]
                if not spots:
                    continue
                boxes = {(rc(i)[0] // 3) * 3 + rc(i)[1] // 3 for i in spots}
                if len(boxes) == 1:
                    b_idx = next(iter(boxes))
                    b_ids = {ic(*cell) for cell in BOXES[b_idx]}
                    log.begin_step(grid)
                    removed = []
                    for i in b_ids:
                        if i not in u_ids and grid.is_empty(i) and d in grid.cands[i]:
                            if grid.eliminate(i, d):
                                removed.append((rc(i)[0], rc(i)[1], d))
                    if removed:
                        log.record(grid, "box_line_reduction", None, None, None, removed,
                                   f"Box-line reduction — in this {kind}, digit {d} can only go "
                                   f"in one box, so {d} is removed from that box outside the {kind}.")
                        return True
                    log.discard_step()
    return False


# ---------------------------------------------------------------------------
# Basic coloring (single-digit chains of length 2)
# ---------------------------------------------------------------------------

@register("Coloring (Basic)", 10)
def color_basics(grid: Grid, log: Log) -> bool:
    """Single-digit 2-chain coloring: if a digit has exactly two candidates
    in a unit, and one of them shares a unit with a third candidate that
    also sees the other, eliminate the third.

    This is the simplest form of "simple coloring" / "color trap".
    """
    for d in range(1, 10):
        cells = grid.cells_with(d)
        if len(cells) < 3:
            continue
        # For each pair of cells in the same unit (the "strong link"),
        # find a third cell that sees both.
        for unit in (ROWS, COLS, BOXES):
            for u in unit:
                u_ids = {ic(*cell) for cell in u}
                in_unit = [i for i in cells if i in u_ids]
                if len(in_unit) != 2:
                    continue
                a, b = in_unit
                for c in cells:
                    if c in (a, b):
                        continue
                    # c must see both a and b
                    if _sees(a, c) and _sees(b, c):
                        r, col = rc(c)
                        log.begin_step(grid)
                        if grid.eliminate(c, d):
                            log.record(grid, "coloring_basic", r, col, None,
                                       [(r, col, d)],
                                       f"Simple coloring — digit {d} has a strong link at "
                                       f"{grid.fmt_cell(a)}/{grid.fmt_cell(b)} in this unit. "
                                       f"Cell {grid.fmt_cell(c)} sees both ends of the link, "
                                       f"so it cannot be {d}.")
                            return True
                        log.discard_step()
    return False


def _sees(a: int, b: int) -> bool:
    """True if cells a and b share a row, column, or box."""
    ra, ca = rc(a)
    rb, cb = rc(b)
    return ra == rb or ca == cb or (ra // 3 == rb // 3 and ca // 3 == cb // 3)
