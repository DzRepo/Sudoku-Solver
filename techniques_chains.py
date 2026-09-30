"""Alternating Inference Chains (AIC) for a single digit.

An AIC is a chain of cells (all candidates of one digit d) linked by
alternating strong and weak links:

* strong link: two cells in the same unit where d appears in exactly two
  cells (exactly one is d).
* weak link:   two cells that see each other (at most one is d).

The chain starts and ends on a strong link. If the two ends see a third
cell that also has d as a candidate, that cell cannot be d.

This generalizes X-Wing (a 4-cell AIC) and is the workhorse for very hard
puzzles. We search with DFS up to a bounded length.
"""

from typing import Dict, List, Set

from advanced import (
    BOXES, COLS, ROWS, Grid, Log, ic, rc, register,
)

MAX_CHAIN = 7  # odd number of cells (even number of links)


def _sees(a: int, b: int) -> bool:
    ra, ca = rc(a)
    rb, cb = rc(b)
    return ra == rb or ca == cb or (ra // 3 == rb // 3 and ca // 3 == cb // 3)


def _build_links(d: int, grid: Grid):
    """Return (strong, weak) adjacency maps for digit d.

    strong[a] = list of cells b such that a-b is a strong link.
    weak[a]   = list of cells b such that a-b is a weak link (sees a).
    """
    cells = sorted(grid.cells_with(d))
    strong: Dict[int, List[int]] = {i: [] for i in cells}
    weak: Dict[int, List[int]] = {i: [] for i in cells}
    # strong links: units where d appears in exactly two cells
    for unit in (ROWS, COLS, BOXES):
        for u in unit:
            spots = [ic(*c) for c in u if d in grid.cands[ic(*c)]]
            if len(spots) == 2:
                a, b = spots
                strong[a].append(b)
                strong[b].append(a)
    # weak links: cells that see each other
    for i in cells:
        for j in cells:
            if i != j and _sees(i, j):
                weak[i].append(j)
    return strong, weak


def _find_aic(grid: Grid, log: Log, d: int) -> bool:
    strong, weak = _build_links(d, grid)
    cells = sorted(strong)
    if not cells:
        return False
    seen_chains = set()

    def dfs(start: int, path: List[int], cur: int, depth: int,
            last_strong: bool) -> bool:
        # A valid AIC: length >= 3, starts & ends on strong links.
        if depth >= 3 and last_strong:
            key = frozenset(path)
            if key in seen_chains:
                return False
            seen_chains.add(key)
            # ends are path[0] and cur; they must see a common viewer
            a, b = path[0], cur
            log.begin_step(grid)
            removed = []
            # Copy: grid.eliminate() mutates cand_cells[d] below.
            for k in sorted(grid.cells_with(d)):
                if k in (a, b) or k in path:
                    continue
                if _sees(k, a) and _sees(k, b):
                    if grid.eliminate(k, d):
                        removed.append((rc(k)[0], rc(k)[1], d))
            if removed:
                chain_str = " -> ".join(grid.fmt_cell(x) for x in path)
                log.record(grid, "aic", None, None, None, removed,
                           f"AIC — digit {d} forms an alternating inference "
                           f"chain: {chain_str}. The two ends "
                           f"{grid.fmt_cell(a)} and {grid.fmt_cell(b)} see "
                           f"each other's viewer, so that cell cannot be {d}.",
                           f"Chosen because no simpler technique applied; the "
                           f"AIC on {d} forces the elimination.")
                return True
            log.discard_step()
        if depth >= MAX_CHAIN:
            return False
        # next link must alternate: if last was strong, next is weak, and vice versa
        nxt_links = weak[cur] if last_strong else strong[cur]
        for nxt in nxt_links:
            if nxt in path:
                continue
            if nxt == start and depth < 2:
                continue
            if dfs(start, path + [nxt], nxt, depth + 1, not last_strong):
                return True
        return False

    for start in cells:
        if not strong[start]:
            continue
        # first link must be strong
        for nxt in strong[start]:
            if dfs(start, [start, nxt], nxt, 2, True):
                return True
    return False


@register("AIC (Alternating Inference Chain)", 17)
def aic(grid: Grid, log: Log) -> bool:
    for d in range(1, 10):
        if _find_aic(grid, log, d):
            return True
    return False
