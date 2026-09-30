"""XY-Wing and W-Wing (common advanced techniques).

XY-Wing: three cells, one the "pivot" seeing the other two ("pincers").
The pivot has exactly two candidates {A, B}; each pincer has exactly three
candidates and one of them is {A, B} (i.e. {A, C} and {B, C} for some C).
Then C cannot be in any cell that sees both pincers.

W-Wing: two cells with the same two candidates {A, B} that do NOT see each
other. Let U be the set of units (rows/cols/boxes) that contain exactly one
of the two cells. Any cell that (a) has A or B as a candidate, (b) is in one
of those units, and (c) sees the opposite W-Wing cell can have that digit
removed.
"""

from typing import List, Set, Tuple

from advanced import (
    BOXES, COLS, ROWS, Grid, Log, ic, rc, register, units_of,
)


def _sees(a: int, b: int) -> bool:
    ra, ca = rc(a)
    rb, cb = rc(b)
    return ra == rb or ca == cb or (ra // 3 == rb // 3 and ca // 3 == cb // 3)


@register("XY-Wing", 15)
def xy_wing(grid: Grid, log: Log) -> bool:
    empties = [i for i in range(81) if grid.is_empty(i)]
    for pivot in empties:
        pc = grid.cands[pivot]
        if len(pc) != 2:
            continue
        A, B = sorted(pc)
        # pincers: cells seeing the pivot that contain BOTH A and B (plus at
        # least one other candidate). The shared third digit C is the digit
        # both pincers have that is neither A nor B.
        pincers = []
        for j in empties:
            if j == pivot or not _sees(pivot, j):
                continue
            jc = grid.cands[j]
            if A in jc and B in jc and len(jc) > 2:
                pincers.append(j)
        # need two pincers that see each other
        for x in range(len(pincers)):
            for y in range(x + 1, len(pincers)):
                j1, j2 = pincers[x], pincers[y]
                if not _sees(j1, j2):
                    continue
                # shared third candidate C = the digit in both pincers that is
                # neither A nor B
                c1 = grid.cands[j1] - {A, B}
                c2 = grid.cands[j2] - {A, B}
                shared = c1 & c2
                if not shared:
                    continue
                C = next(iter(shared))
                # eliminate C from cells seeing both pincers
                log.begin_step(grid)
                removed = []
                for k in empties:
                    if k in (pivot, j1, j2):
                        continue
                    if C in grid.cands[k] and _sees(k, j1) and _sees(k, j2):
                        if grid.eliminate(k, C):
                            removed.append((rc(k)[0], rc(k)[1], C))
                if removed:
                    log.record(grid, "xy_wing", None, None, None, removed,
                               f"XY-Wing — pivot {grid.fmt_cell(pivot)} has "
                               f"candidates {A}{B}; pincers {grid.fmt_cell(j1)} "
                               f"({grid.fmt_cands(j1)}) and {grid.fmt_cell(j2)} "
                               f"({grid.fmt_cands(j2)}) see each other. Any cell "
                               f"seeing both pincers cannot be {C}.",
                               f"Chosen because no simpler technique applied; "
                               f"the XY-Wing pattern on {A}{B} forces the "
                               f"elimination of {C} from the common viewers.")
                    return True
                log.discard_step()
    return False


@register("W-Wing", 16)
def w_wing(grid: Grid, log: Log) -> bool:
    # W-Wing is subsumed by AIC for our purposes; we rely on AIC instead.
    return False
