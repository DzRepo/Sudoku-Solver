"""Tiny web server for the Sudoku solver app.

Standard library only — no dependencies to install.
Run:  python server.py [port]     (default port 8000)

Endpoints:
    GET  /            -> static files (index.html, style.css, app.js)
    POST /api/solve   -> {"grid": [81 ints]}  => solver result with step log
"""

import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from random import randrange

import solver

ROOT = Path(__file__).parent
CSV_PATH = ROOT / "sudoku.csv"
HEADER_LEN = 16  # len(b"puzzle,solution\n")
ROW_LEN = 164    # 81 digits + comma + 81 digits + newline


def read_random_puzzle():
    """Return a uniformly random puzzle (81-char string) from sudoku.csv.

    Every data row is exactly 164 bytes (81 + comma + 81 + newline), so a
    random row index maps to an exact byte offset — an O(1) read instead of
    scanning the whole ~1.4 GB file.
    """
    size = os.path.getsize(CSV_PATH)
    nrows = (size - HEADER_LEN) // ROW_LEN
    if nrows <= 0:
        raise ValueError("no puzzles in sudoku.csv")
    with CSV_PATH.open("rb") as f:
        for _ in range(8):  # bounded retries in case the file layout differs
            off = HEADER_LEN + randrange(nrows) * ROW_LEN
            f.seek(off)
            line = f.readline()
            puzzle = line.split(b",")[0].strip()
            if len(line) == ROW_LEN and len(puzzle) == 81 and puzzle.isdigit():
                return puzzle.decode("ascii")
    raise ValueError("no valid puzzle found in sudoku.csv")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/examples":
            self._send(200, solver.EXAMPLES)
            return
        if path == "/api/random":
            self._random_puzzle()
            return
        if path == "/api/health":
            self._send(200, {"status": "ok"})
            return
        rel = path.lstrip("/") or "index.html"
        file_path = (ROOT / rel).resolve()
        if not str(file_path).startswith(str(ROOT.resolve())):
            self._send(403, {"error": "forbidden"})
            return
        if not file_path.is_file():
            self._send(404, {"error": "not found"})
            return
        ctype = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/api/solve":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, UnicodeDecodeError):
            self._send(400, {"error": "invalid JSON body"})
            return

        grid = payload.get("grid")
        if (not isinstance(grid, list) or len(grid) != 81
                or not all(isinstance(v, int) and 0 <= v <= 9 for v in grid)):
            self._send(400, {"error": "grid must be a list of 81 integers (0-9)"})
            return

        result = solver.solve(grid)
        self._send(200, result)

    def _random_puzzle(self):
        """Return a uniformly random puzzle from sudoku.csv.

        The file is ~9 million fixed-width rows (~1.4 GB), so instead of
        scanning it we seek to a random byte offset and read the row that
        contains it — an O(1) read.
        """
        if not CSV_PATH.is_file():
            self._send(404, {"error": "sudoku.csv not found"})
            return
        try:
            puzzle = read_random_puzzle()
        except ValueError:
            self._send(404, {"error": "no puzzles in sudoku.csv"})
            return
        except Exception:
            self._send(500, {"error": "failed to read sudoku.csv"})
            return
        self._send(200, {"grid": [int(ch) for ch in puzzle]})

    def log_message(self, fmt, *args):
        sys.stderr.write("[sudoku] " + (fmt % args) + "\n")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Sudoku solver running at http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
