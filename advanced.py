"""Core Sudoku grid model and candidate framework.

Everything in the solver is built on top of :class:`Grid`:

* ``grid[i]``        – the placed value (0 = empty)
* ``grid.cands[i]``  – the set of candidate digits for an empty cell
* ``grid.cand_cells`` – inverse index: digit -> set of cells that can take it

Techniques receive a ``Grid`` plus a :class:`Log` and either return
``True`` (they eliminated at least one candidate / placed a value, and
recorded their reasoning in the log) or ``False`` (nothing to do).

The log captures every action with a human-readable explanation so the
web UI can replay and explain the entire solution.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

Cell = Tuple[int, int]  # (row, col), 0-indexed
Unit = List[Cell]       # a row, column, or box


@dataclass
class Step:
    """One recorded action of the solver."""
    technique: str
    row: Optional[int]
    col: Optional[int]
    value: Optional[int]
    eliminated: List[Tuple[int, int, int]]  # (row, col, digit) removed
    reason: str
    detail: str = ""

    def to_dict(self):
        return {
            "type": self.technique,
            "row": self.row,
            "col": self.col,
            "value": self.value,
            "eliminated": [list(e) for e in self.eliminated],
            "reason": self.reason,
            "detail": self.detail,
        }


class Log:
    """Collects :class:`Step` objects and the board history.

    ``boards`` holds one snapshot *before* each step, plus a final snapshot
    after the last step: ``len(boards) == len(steps) + 1`` and
    ``boards[n] + steps[n] -> boards[n+1]``. Call ``begin_step(grid)`` with
    the pre-mutation grid before applying a step's changes, then
    ``record(...)`` to append the step.
    """

    def __init__(self):
        self.steps: List[Step] = []
        self.boards: List[List[int]] = []  # board snapshot before each step
        self.cands: List[List[List[int]]] = []  # candidate snapshot before each step
        self._pending: Optional[List[int]] = None  # pre-step snapshot
        self._pending_cands: Optional[List[List[int]]] = None  # pre-step candidates

    def begin_step(self, grid: "Grid") -> None:
        """Snapshot the board *and* candidates *before* the next step's mutation."""
        self._pending = list(grid.values)
        self._pending_cands = [sorted(grid.cands[i]) for i in range(81)]

    def discard_step(self) -> None:
        """Drop a pending pre-step snapshot (the step turned out to be a no-op)."""
        self._pending = None
        self._pending_cands = None

    def record(self, grid: "Grid", technique: str, row: Optional[int],
               col: Optional[int], value: Optional[int],
               eliminated: List[Tuple[int, int, int]], reason: str,
               detail: str = "") -> Step:
        if self._pending is not None:
            self.boards.append(self._pending)
            self.cands.append(self._pending_cands)
            self._pending = None
            self._pending_cands = None
        else:
            # No begin_step() call: fall back to the grid as passed in.
            self.boards.append(list(grid.values))
            self.cands.append([sorted(grid.cands[i]) for i in range(81)])
        step = Step(technique, row, col, value, eliminated, reason, detail)
        self.steps.append(step)
        return step

    def finalize(self, grid: "Grid") -> None:
        """Append the final board + candidate snapshot (state after the last step)."""
        self.boards.append(list(grid.values))
        self.cands.append([sorted(grid.cands[i]) for i in range(81)])


# ---------------------------------------------------------------------------
# Unit tables (precomputed once)
# ---------------------------------------------------------------------------

def _build_units():
    rows = [[(r, c) for c in range(9)] for r in range(9)]
    cols = [[(r, c) for r in range(9)] for c in range(9)]
    boxes = []
    for br in range(0, 9, 3):
        for bc in range(0, 9, 3):
            boxes.append([(br + i, bc + j) for i in range(3) for j in range(3)])
    return rows, cols, boxes


ROWS, COLS, BOXES = _build_units()
UNITS = ROWS + COLS + BOXES  # 27 units

UNIT_NAMES = [f"Row {i+1}" for i in range(9)] + \
             [f"Col {i+1}" for i in range(9)] + \
             [f"Box {i+1}" for i in range(9)]


def units_of(r: int, c: int) -> List[List[Cell]]:
    """The three units (row, column, box) containing cell (r, c)."""
    return [ROWS[r], COLS[c], BOXES[(r // 3) * 3 + c // 3]]


def rc(i: int) -> Cell:
    return (i // 9, i % 9)


def ic(r: int, c: int) -> int:
    return r * 9 + c


# ---------------------------------------------------------------------------
# Grid
# ---------------------------------------------------------------------------

class Grid:
    """Mutable 9x9 Sudoku state with candidate bookkeeping."""

    __slots__ = ("values", "cands", "cand_cells")

    def __init__(self, values: Optional[List[int]] = None):
        if values is None:
            values = [0] * 81
        self.values = list(values)
        self.cands: List[Set[int]] = [set() for _ in range(81)]
        self.cand_cells: List[Set[int]] = [set() for _ in range(10)]  # 1..9
        self._rebuild_candidates()

    # -- candidate management ---------------------------------------------

    def _rebuild_candidates(self):
        """Recompute all candidates from scratch (used on init)."""
        for i in range(81):
            if self.values[i] == 0:
                r, c = rc(i)
                used = set()
                for unit in units_of(r, c):
                    for (rr, cc) in unit:
                        used.add(self.values[ic(rr, cc)])
                self.cands[i] = set(range(1, 10)) - used
        self._rebuild_cand_cells()

    def _rebuild_cand_cells(self):
        self.cand_cells = [set() for _ in range(10)]
        for i in range(81):
            for d in self.cands[i]:
                self.cand_cells[d].add(i)

    def is_empty(self, i: int) -> bool:
        return self.values[i] == 0

    def candidates(self, i: int) -> Set[int]:
        return self.cands[i]

    def cells_with(self, d: int) -> Set[int]:
        """Cells that still have digit d as a candidate."""
        return self.cand_cells[d]

    def cell_in_unit(self, i: int, unit: List[Cell]) -> bool:
        return ic(*rc(i)) in {ic(*cell) for cell in unit}

    # -- mutations (return True if anything changed) ------------------------

    def place(self, i: int, d: int) -> bool:
        """Place digit d in cell i, eliminating it everywhere else."""
        if self.values[i] != 0:
            return False
        r, c = rc(i)
        self.values[i] = d
        self.cands[i] = set()
        changed = False
        for unit in units_of(r, c):
            for (rr, cc) in unit:
                j = ic(rr, cc)
                if j != i and d in self.cands[j]:
                    self.cands[j].discard(d)
                    self.cand_cells[d].discard(j)
                    changed = True
        return changed

    def eliminate(self, i: int, d: int) -> bool:
        """Remove candidate d from cell i.

        Returns True if d was actually present (and removed). If the cell
        becomes a naked single, it is placed automatically.
        """
        if d not in self.cands[i]:
            return False
        self.cands[i].discard(d)
        self.cand_cells[d].discard(i)
        if len(self.cands[i]) == 1:
            only = next(iter(self.cands[i]))
            self.place(i, only)
        return True

    def eliminated_cells(self, d: int) -> Set[int]:
        return self.cand_cells[d]

    # -- helpers for explanations ------------------------------------------

    def fmt_cell(self, i: int) -> str:
        r, c = rc(i)
        return f"R{r+1}C{c+1}"

    def fmt_digit(self, d: int) -> str:
        return str(d)

    def fmt_cands(self, i: int) -> str:
        return "".join(str(x) for x in sorted(self.cands[i]))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate(values: List[int]) -> List[str]:
    """Return a list of human-readable conflicts among the given clues."""
    errors = []
    for unit, name in zip(UNITS, UNIT_NAMES):
        seen = {}
        for (r, c) in unit:
            v = values[ic(r, c)]
            if not v:
                continue
            if v in seen:
                pr, pc = seen[v]
                errors.append(
                    f"{name} contains two {v}s — at R{pr+1}C{pc+1} and "
                    f"R{r+1}C{c+1}. The clues conflict, so the puzzle has no solution."
                )
            else:
                seen[v] = (r, c)
    return errors


# ---------------------------------------------------------------------------
# Technique registry
# ---------------------------------------------------------------------------

# Each entry: (name, function(grid, log) -> bool, priority)
# Lower priority number = tried earlier. The solver loops over the whole
# list until a full pass makes no progress, then moves on.
TECHNIQUES: List[Tuple[str, Callable[[Grid, Log], bool], int]] = []


def register(name: str, priority: int = 100):
    """Decorator to register a technique function."""
    def deco(fn):
        TECHNIQUES.append((name, fn, priority))
        return fn
    return deco


def all_techniques() -> List[Tuple[str, Callable[[Grid, Log], bool]]]:
    """Techniques sorted by priority (stable)."""
    ordered = sorted(TECHNIQUES, key=lambda t: t[2])
    return [(n, f) for n, f, _ in ordered]
