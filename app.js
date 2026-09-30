/* Sudoku solver front-end: board editing + animated step-by-step replay. */

const state = {
  grid: new Array(81).fill(0),   // current board values (0 = empty)
  cands: new Array(81).fill(null), // candidate sets per cell (null = unknown)
  tech: new Array(81).fill(null), // technique class per cell (naked/hidden-single/guess)
  givens: new Set(),             // indices the user typed in (shown bold blue)
  selected: null,                // currently clicked cell index
  animToken: 0,                  // bump to cancel a running animation
  boards: [],                    // authoritative board snapshot before each step
  cursnap: [],                   // authoritative candidate snapshot before each step
  cursor: -1,                    // current step index during replay
  steps: [],                     // full step list from the server
  givensSet: new Set(),          // givens at solve time (for replay rendering)
  stepMode: false,               // true while in single-step mode
};

const boardEl = document.getElementById("board");
const logEl = document.getElementById("log");
const statusEl = document.getElementById("status");
const counterEl = document.getElementById("step-counter");
const solveBtn = document.getElementById("solve-btn");
const stopBtn = document.getElementById("stop-btn");
const stepBtn = document.getElementById("step-btn");
const pencilBtn = document.getElementById("pencil-btn");

/* ---------------- board rendering ---------------- */

function buildBoard() {
  boardEl.innerHTML = "";
  for (let i = 0; i < 81; i++) {
    const cell = document.createElement("div");
    cell.className = "cell";
    cell.dataset.idx = i;
    cell.addEventListener("click", () => selectCell(i));
    boardEl.appendChild(cell);
  }
}

function cellEl(i) { return boardEl.children[i]; }

function renderPencil(i, el) {
  const old = el.querySelector(".pencil");
  if (old) old.remove();
  const cands = state.cands[i];
  if (!cands) return;
  const p = document.createElement("div");
  p.className = "pencil";
  for (let d = 1; d <= 9; d++) {
    const s = document.createElement("span");
    if (cands.includes(d)) s.textContent = d;
    p.appendChild(s);
  }
  el.appendChild(p);
}

function renderCell(i, flash = false) {
  const el = cellEl(i);
  const v = state.grid[i];
  el.textContent = v ? String(v) : "";
  el.classList.remove("given", "naked", "hidden-single", "guess");
  if (v) {
    const cls = state.givens.has(i) ? "given" : state.tech[i];
    if (cls) el.classList.add(cls);
  }
  if (!v) renderPencil(i, el);
  if (flash) {
    el.classList.remove("flash");
    void el.offsetWidth; // restart animation
    el.classList.add("flash");
  }
}

function renderAll() { for (let i = 0; i < 81; i++) renderCell(i); }

function selectCell(i) {
  if (state.selected !== null) cellEl(state.selected).classList.remove("selected");
  state.selected = i;
  cellEl(i).classList.add("selected");
}

/* ---------------- number pad ---------------- */

function buildNumpad() {
  const pad = document.createElement("div");
  pad.className = "numpad";
  for (let d = 1; d <= 9; d++) {
    const b = document.createElement("button");
    b.textContent = d;
    b.addEventListener("click", () => setCell(d));
    pad.appendChild(b);
  }
  const erase = document.createElement("button");
  erase.className = "erase";
  erase.textContent = "Erase";
  erase.addEventListener("click", () => setCell(0));
  pad.appendChild(erase);
  boardEl.after(pad);
}

function setCell(d) {
  if (state.selected === null || state.animating) return;
  const i = state.selected;
  if (state.givens.has(i) && d !== 0) return; // givens are locked
  state.grid[i] = d;
  if (d === 0) { state.givens.delete(i); state.tech[i] = null; }
  else { state.givens.add(i); state.tech[i] = null; }
  renderCell(i, true);
}

/* keyboard entry: digits + backspace */
document.addEventListener("keydown", (e) => {
  if (state.animating || state.selected === null) return;
  if (/^[1-9]$/.test(e.key)) setCell(Number(e.key));
  else if (e.key === "Backspace" || e.key === "0") setCell(0);
});

/* ---------------- examples ---------------- */

async function loadExamples() {
  const sel = document.getElementById("example-select");
  try {
    const res = await fetch("/api/examples");
    const examples = await res.json();
    for (const ex of examples) {
      const opt = document.createElement("option");
      opt.value = JSON.stringify(ex.grid);
      opt.textContent = ex.name;
      sel.appendChild(opt);
    }
  } catch { /* server offline — examples just unavailable */ }
}

document.getElementById("load-example").addEventListener("click", () => {
  const sel = document.getElementById("example-select");
  if (!sel.value) return;
  stopAnimation();
  state.grid = JSON.parse(sel.value);
  state.cands.fill(null);
  state.tech.fill(null);
  state.givens = new Set(state.grid.map((v, i) => (v ? i : -1)).filter(i => i >= 0));
  state.givensSet.clear();
  state.steps = [];
  state.cursor = -1;
  state.selected = null;
  pencilBtn.classList.remove("active");
  clearLog();
  setStatus("");
  renderAll();
});

/* ---------------- log ---------------- */

const TAG_NAMES = {
  naked_single: "Naked single",
  hidden_single: "Hidden single",
  naked_subset: "Naked subset",
  hidden_subset: "Hidden subset",
  pointing_pair: "Pointing pair",
  box_line_reduction: "Box-line reduction",
  coloring_basic: "Coloring",
  fish: "Fish",
  x_cycle: "X-Cycle",
  xy_wing: "XY-Wing",
  w_wing: "W-Wing",
  aic: "AIC",
  guess: "Guess",
  backtrack: "Backtrack",
  search_fallback: "Search fallback",
  done: "Solved",
  error: "Error",
};

function clearLog() { logEl.innerHTML = ""; counterEl.textContent = ""; }

function addLogEntry(step, n) {
  const li = document.createElement("li");
  li.className = step.type;
  const reason = step.reason.replace(/R(\d)C(\d)/g, '<span class="cellref">R$1C$2</span>');
  const detail = step.detail
    ? `<div class="detail">${step.detail.replace(/R(\d)C(\d)/g, '<span class="cellref">R$1C$2</span>')}</div>`
    : "";
  li.innerHTML = `<span class="num">${n}</span><span class="tag">${TAG_NAMES[step.type] || step.type}</span><div>${reason}</div>${detail}`;
  logEl.appendChild(li);
  counterEl.textContent = `${n} step${n === 1 ? "" : "s"}`;
  logEl.scrollTop = logEl.scrollHeight;
}

function setStatus(msg, cls = "") {
  statusEl.textContent = msg;
  statusEl.className = "status" + (cls ? " " + cls : "");
}

/* ---------------- solving & animation ---------------- */

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function solve() {
  if (state.stepMode) {
    // Exit step mode without the stop-animation side effects.
    state.stepMode = false;
    state.animToken++;
    state.steps = [];
    state.cursor = -1;
  }
  const payload = state.grid.slice();
  if (payload.every((v) => v === 0)) { setStatus("Enter at least one clue first.", "err"); return; }

  state.animating = true;
  solveBtn.classList.add("hidden");
  stopBtn.classList.remove("hidden");
  setStatus("Solving…");

  let result;
  try {
    const res = await fetch("/api/solve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ grid: payload }),
    });
    result = await res.json();
  } catch {
    setStatus("Could not reach the solver server.", "err");
    return finishAnimation();
  }

  const speed = Number(document.getElementById("speed-select").value);
  const token = ++state.animToken;

  // The server sends an authoritative board snapshot *before* each step
  // (boards[n]) plus a final snapshot after the last step (boards[-1]).
  // For step n we render boards[n+1] (the post-step board) so the step's
  // effect is visible immediately. Rendering snapshots directly (instead of
  // accumulating placements) keeps the UI in lock-step with the server —
  // elimination-only steps auto-place naked singles on the server side, so
  // replaying only placements would desync the board.
  const steps = result.steps;
  const boards = result.boards && result.boards.length
    ? result.boards
    : buildBoards(result); // fallback if a server omits snapshots
  const cands = result.cands && result.cands.length
    ? result.cands
    : buildCands(result, boards); // fallback if a server omits candidates
  const givens = new Set(payload.map((v, i) => (v ? i : -1)).filter((i) => i >= 0));
  state.boards = boards;
  state.cursnap = cands;
  state.givens = givens;

  for (let n = 0; n < steps.length; n++) {
    if (token !== state.animToken) return; // user pressed Stop
    const step = steps[n];
    state.cursor = n;
    renderStep(n, boards, cands, step, givens);
    addLogEntry(step, n + 1);

    if (step.type === "done") setStatus("Solved! See the log for how.", "ok");
    if (step.type === "error") setStatus("This puzzle has no solution.", "err");

    // Search (guess/backtrack) runs are noisy; fast-forward them so a
    // search-assisted solve still finishes promptly.
    const delay = (step.type === "guess" || step.type === "backtrack")
      ? Math.min(speed, 8)
      : speed;
    if (delay > 0) await sleep(delay);
  }

  // Land on the final solved grid (the server's authoritative result).
  if (token === state.animToken) {
    const finalBoard = (result.grid && result.grid.length === 81)
      ? result.grid
      : (boards.length ? boards[boards.length - 1] : payload);
    state.grid = finalBoard.slice();
    renderAll();
  }
  finishAnimation();
}

/* Render the board as it is *after* step n (boards[n+1]), then highlight the
   cell (or cells) that step n touches. boards[n] is the pre-step snapshot,
   so rendering boards[n+1] shows the step's effect (placement or
   elimination) immediately — the highlighted cell is already filled. */
function renderStep(n, boards, cands, step, givens) {
  const board = boards[n + 1] || boards[boards.length - 1] || state.grid;
  const candSnap = cands[n + 1] || cands[cands.length - 1] || null;
  for (let i = 0; i < 81; i++) {
    state.grid[i] = board[i];
    state.cands[i] = candSnap ? candSnap[i] : null;
  }

  // Technique colour for the cell this step placed (if any).
  state.tech.fill(null);
  let hi = -1;
  if (step.row !== null && step.col !== null) {
    hi = step.row * 9 + step.col;
    if (step.value) {
      state.tech[hi] = step.type === "naked_single" ? "naked"
                   : step.type === "hidden_single" ? "hidden-single"
                   : step.type === "guess" ? "guess" : "";
    }
  }

  for (let i = 0; i < 81; i++) {
    const el = cellEl(i);
    const v = state.grid[i];
    el.textContent = v ? String(v) : "";
    el.classList.remove("given", "naked", "hidden-single", "guess", "current");
    // classList.add("") throws, so only add when we have a real token.
    if (v) {
      const cls = givens.has(i) ? "given" : state.tech[i];
      if (cls) el.classList.add(cls);
    } else {
      renderPencil(i, el);
    }
    if (i === hi) el.classList.add("current");
    if (i === hi && step.value) {
      el.classList.remove("flash");
      void el.offsetWidth; // restart animation
      el.classList.add("flash");
    }
  }
}

/* Reconstruct board snapshots from steps when a server doesn't send them.
   Not used by the current server (which always sends `boards`), but keeps
   the replay robust. */
function buildBoards(result) {
  const boards = [result.initial_grid.slice()];
  let cur = result.initial_grid.slice();
  const snaps = [];
  for (const step of result.steps) {
    boards.push(cur.slice());
    if (step.row === null || step.col === null) continue;
    const i = step.row * 9 + step.col;
    if (step.type === "guess") { snaps.push(cur.slice()); cur[i] = step.value; }
    else if (step.type === "backtrack") { cur = (snaps.pop() || cur).slice(); }
    else if (step.value) { cur[i] = step.value; }
  }
  return boards;
}

/* Derive candidate snapshots from board snapshots (fallback when the server
   doesn't send `cands`).  Candidates = digits 1-9 minus those already placed
   in the same row, column, or box. */
function buildCands(result, boards) {
  const cands = boards.map((board) => {
    const out = [];
    for (let i = 0; i < 81; i++) {
      if (board[i] !== 0) { out.push([]); continue; }
      const r = Math.floor(i / 9), c = i % 9;
      const br = Math.floor(r / 3) * 3, bc = Math.floor(c / 3) * 3;
      const used = new Set();
      for (let k = 0; k < 9; k++) {
        used.add(board[r * 9 + k]);
        used.add(board[k * 9 + c]);
        used.add(board[(br + Math.floor(k / 3)) * 9 + bc + (k % 3)]);
      }
      used.delete(0);
      const s = [];
      for (let d = 1; d <= 9; d++) if (!used.has(d)) s.push(d);
      out.push(s);
    }
    return out;
  });
  return cands;
}

/* Compute candidates for a single board (used by the pencil-mark toggle). */
function computeCands(board) {
  const out = [];
  for (let i = 0; i < 81; i++) {
    if (board[i] !== 0) { out.push([]); continue; }
    const r = Math.floor(i / 9), c = i % 9;
    const br = Math.floor(r / 3) * 3, bc = Math.floor(c / 3) * 3;
    const used = new Set();
    for (let k = 0; k < 9; k++) {
      used.add(board[r * 9 + k]);
      used.add(board[k * 9 + c]);
      used.add(board[(br + Math.floor(k / 3)) * 9 + bc + (k % 3)]);
    }
    used.delete(0);
    const s = [];
    for (let d = 1; d <= 9; d++) if (!used.has(d)) s.push(d);
    out.push(s);
  }
  return out;
}

/* ---------------- pencil-mark toggle ---------------- */

function togglePencil() {
  if (state.animating) return;
  if (state.cands.some((c) => c !== null)) {
    // Turn off: clear all candidate data.
    state.cands.fill(null);
    pencilBtn.classList.remove("active");
  } else {
    // Turn on: compute candidates from the current board.
    const c = computeCands(state.grid);
    for (let i = 0; i < 81; i++) state.cands[i] = c[i];
    pencilBtn.classList.add("active");
  }
  renderAll();
}

function stopAnimation() { state.animToken++; finishAnimation(); }

function finishAnimation() {
  state.animating = false;
  state.stepMode = false;
  solveBtn.classList.remove("hidden");
  stopBtn.classList.add("hidden");
}

/* ---------------- single-step mode ---------------- */

async function startStepMode() {
  const payload = state.grid.slice();
  if (payload.every((v) => v === 0)) { setStatus("Enter at least one clue first.", "err"); return; }

  state.animating = true;
  state.stepMode = true;
  solveBtn.classList.add("hidden");
  stopBtn.classList.remove("hidden");
  setStatus("Fetching solution…");

  let result;
  try {
    const res = await fetch("/api/solve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ grid: payload }),
    });
    result = await res.json();
  } catch {
    setStatus("Could not reach the solver server.", "err");
    return finishAnimation();
  }

  const steps = result.steps;
  const boards = result.boards && result.boards.length
    ? result.boards
    : buildBoards(result);
  const cands = result.cands && result.cands.length
    ? result.cands
    : buildCands(result, boards);
  const givens = new Set(payload.map((v, i) => (v ? i : -1)).filter((i) => i >= 0));

  state.steps = steps;
  state.boards = boards;
  state.cursnap = cands;
  state.givens = givens;
  state.givensSet = givens;
  state.cursor = -1;

  // Render the initial board (before any step) so the user sees the starting state.
  for (let i = 0; i < 81; i++) {
    state.grid[i] = boards[0][i];
    state.cands[i] = cands[0] ? cands[0][i] : null;
  }
  state.tech.fill(null);
  renderAll();
  setStatus(`Ready. ${steps.length} step(s) to go. Click Step to advance.`);
}

function doStep() {
  if (state.animating && state.stepMode) {
    // Already in step mode: advance one step.
    if (state.cursor + 1 >= state.steps.length) return;
    const n = state.cursor + 1;
    state.cursor = n;
    const step = state.steps[n];
    renderStep(n, state.boards, state.cursnap, step, state.givensSet);
    addLogEntry(step, n + 1);

    if (step.type === "done") {
      setStatus("Solved! See the log for how.", "ok");
      finishAnimation();
    } else if (step.type === "error") {
      setStatus("This puzzle has no solution.", "err");
      finishAnimation();
    } else {
      setStatus(`Step ${n + 1} of ${state.steps.length}. Click Step to continue.`);
    }
  } else {
    // Not in step mode yet: start it.
    startStepMode();
  }
}

solveBtn.addEventListener("click", solve);
stopBtn.addEventListener("click", stopAnimation);
stepBtn.addEventListener("click", doStep);
pencilBtn.addEventListener("click", togglePencil);

document.getElementById("clear-btn").addEventListener("click", () => {
  stopAnimation();
  state.grid.fill(0);
  state.cands.fill(null);
  state.tech.fill(null);
  state.givens.clear();
  state.givensSet.clear();
  state.steps = [];
  state.cursor = -1;
  state.selected = null;
  pencilBtn.classList.remove("active");
  clearLog();
  setStatus("");
  renderAll();
});

/* ---------------- init ---------------- */

buildBoard();
buildNumpad();
loadExamples();
