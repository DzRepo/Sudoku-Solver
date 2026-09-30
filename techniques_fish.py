"""Fish techniques: X-Wing, Swordfish, Jellyfish, and general N-fish.

An N-fish: digit d has candidates in exactly N rows, and those candidates
all lie in the same N columns -> eliminate d from those columns outside the
N rows. (Symmetric version with rows/columns swapped.)

Also implements the "X-Cycle" family: a closed alternating chain of
strong/weak links for one digit (generalization of X-Wing).
"""

from typing import Dict, List, Set, Tuple

from advanced import (
    BOXES, COLS, ROWS, Grid, Log, ic, rc, register,
)


def _rows_of(d: int, grid: Grid) -> Dict[int, Set[int]]:
    """row -> set of columns where d is a candidate"""
    out: Dict[int, Set[int]] = {}
    for i in grid.cells_with(d):
        r, c = rc(i)
        out.setdefault(r, set()).add(c)
    return out


def _cols_of(d: int, grid: Grid) -> Dict[int, Set[int]]:
    out: Dict[int, Set[int]] = {}
    for i in grid.cells_with(d):
        r, c = rc(i)
        out.setdefault(c, set()).add(r)
    return out


def _try_fish(grid: Grid, log: Log, d: int, n: int,
              primary: Dict[int, Set[int]], use_rows_as_primary: bool) -> bool:
    """Generic N-fish.

    `primary` maps primary-line index -> set of secondary-line indices where
    digit d is a candidate. If exactly `n` primary lines confine d to the
    same `n` secondary lines, eliminate d from those secondary lines outside
    the `n` primary lines.
    """
    active = {k: v for k, v in primary.items() if v}
    if len(active) < n:
        return False
    from itertools import combinations
    for combo in combinations(sorted(active), n):
        sec_union: Set[int] = set()
        for k in combo:
            sec_union |= active[k]
        if len(sec_union) != n:
            continue
        # every d-candidate in those secondary lines must sit in a combo line
        for sec in sec_union:
            for k, v in active.items():
                if sec in v and k not in combo:
                    sec_union = None
                    break
            if sec_union is None:
                break
        if sec_union is None:
            continue
        # and every d-candidate in those primary lines must sit in a combo
        # secondary line (full cover on both sides — a true fish)
        for prim in combo:
            for sec in active[prim]:
                if sec not in sec_union:
                    sec_union = None
                    break
            if sec_union is None:
                break
        if sec_union is None:
            continue
        log.begin_step(grid)
        removed = []
        for i in grid.cells_with(d):
            r, c = rc(i)
            prim, sec = (r, c) if use_rows_as_primary else (c, r)
            if sec in sec_union and prim not in combo:
                if grid.eliminate(i, d):
                    removed.append((r, c, d))
        if removed:
            names = {2: "X-Wing", 3: "Swordfish", 4: "Jellyfish"}
            name = names.get(n, f"{n}-fish")
            log.record(grid, "fish", None, None, None, removed,
                       f"{name} — digit {d} forms an {n}-fish: its candidates in "
                       f"{n} lines are confined to {n} other lines, so {d} is "
                       f"removed from those lines outside the pattern.")
            return True
        log.discard_step()
    return False


@register("X-Wing", 11)
def x_wing(grid: Grid, log: Log) -> bool:
    for d in range(1, 10):
        if _try_fish(grid, log, d, 2, _rows_of(d, grid), True):
            return True
        if _try_fish(grid, log, d, 2, _cols_of(d, grid), False):
            return True
    return False


@register("Swordfish", 12)
def swordfish(grid: Grid, log: Log) -> bool:
    for d in range(1, 10):
        if _try_fish(grid, log, d, 3, _rows_of(d, grid), True):
            return True
        if _try_fish(grid, log, d, 3, _cols_of(d, grid), False):
            return True
    return False


@register("Jellyfish", 13)
def jellyfish(grid: Grid, log: Log) -> bool:
    for d in range(1, 10):
        if _try_fish(grid, log, d, 4, _rows_of(d, grid), True):
            return True
        if _try_fish(grid, log, d, 4, _cols_of(d, grid), False):
            return True
    return False


# ---------------------------------------------------------------------------
# X-Cycles (closed alternating chains for one digit)
# ---------------------------------------------------------------------------

def _x_cycle(grid: Grid, log: Log, d: int, max_len: int = 8) -> bool:
    """Find a closed alternating chain of strong/weak links for digit d.

    A strong link: two cells in the same unit where d appears in exactly
    two cells (one being d implies the other is not, and vice versa).
    A weak link: two cells that see each other (if one is d, the other is not).

    An X-cycle alternates strong/weak and closes on itself. In a closed
    X-cycle, all cells are "on" or all "off" -> any cell that sees two
    consecutive cells of the cycle (one strong, one weak end) can have d
    eliminated.

    Simplified: find a cycle of length >= 4 of strong links forming a
    rectangle (X-Wing is the 4-cycle). Longer cycles are found via DFS.
    """
    # Build strong-link graph for digit d
    strong: Dict[int, List[int]] = {i: [] for i in grid.cells_with(d)}
    for unit in (ROWS, COLS, BOXES):
        for u in unit:
            u_ids = [ic(*cell) for cell in u]
            spots = [i for i in u_ids if d in grid.cands[i]]
            if len(spots) == 2:
                a, b = spots
                strong[a].append(b)
                strong[b].append(a)

    # DFS for cycles of length 4..max_len
    visited_cycles = set()

    def dfs(start: int, path: List[int], current: int, depth: int):
        if depth > max_len:
            return False
        if depth >= 4 and current == start:
            key = frozenset(path)
            if key in visited_cycles:
                return False
            visited_cycles.add(key)
            # try to eliminate: for each cell in cycle, any cell seeing
            # two consecutive cycle cells (where the link between them is
            # strong) can have d removed.
            log.begin_step(grid)
            removed = []
            cycle = path
            for idx, cell in enumerate(cycle):
                nxt = cycle[(idx + 1) % len(cycle)]
                # cells that see both `cell` and `nxt`
                # Copy: grid.eliminate() mutates cand_cells[d] below.
                for other in sorted(grid.cells_with(d)):
                    if other in cycle or other in (cell, nxt):
                        continue
                    if _sees(other, cell) and _sees(other, nxt):
                        if grid.eliminate(other, d):
                            removed.append((rc(other)[0], rc(other)[1], d))
            if removed:
                log.record(grid, "x_cycle", None, None, None, removed,
                           f"X-Cycle — digit {d} forms a closed alternating chain "
                           f"of {len(cycle)} strong links. Any cell seeing two "
                           f"consecutive cells of the cycle cannot be {d}; "
                           f"those eliminations are applied.")
                return True
            log.discard_step()
            return False
        for nxt in strong.get(current, []):
            if nxt == start and depth < 4:
                continue
            if nxt in path:
                continue
            if dfs(start, path + [nxt], nxt, depth + 1):
                return True
        return False

    for start in sorted(strong):
        if len(strong[start]) < 2:
            continue
        if dfs(start, [start], start, 1):
            return True
    return False


@register("X-Cycle", 14)
def x_cycle(grid: Grid, log: Log) -> bool:
    for d in range(1, 10):
        if _x_cycle(grid, log, d):
            return True
    return False


def _sees(a: int, b: int) -> bool:
    ra, ca = rc(a)
    rb, cb = rc(b)
    return ra == rb or ca == cb or (ra // 3 == rb // 3 and ca // 3 == cb // 3)
