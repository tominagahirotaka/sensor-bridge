"""A tiny, dependency-free import-timing helper shared by get.py/plot.py
for their own top-level heavy imports (numpy, PyQt5, scipy, the mylib
package, ...), so a genuinely slow one (antivirus real-time scanning of a
compiled extension, a slow network-mounted profile dir) shows up as a
specific, numbered, timestamped console line instead of a silently
frozen terminal.

Deliberately lives at the repo root, not inside mylib/ -- importing
mylib.anything runs mylib/__init__.py, which itself imports matplotlib
(for font setup), so fetching this helper from inside that package would
silently pay that cost, untimed, before the first timed import even
starts. Importing nothing beyond the standard library keeps that from
happening.
"""
import contextlib
import time


@contextlib.contextmanager
def timed_import(label, step, total):
    """Print progress before/after the import wrapped in this `with`
    block. `step`/`total` are a fixed position in that script's own list
    of timed imports (e.g. 4/5), not the order they actually happen in at
    runtime -- some (like plot.py's PyPDF2) only run later, on demand, so
    the number stays meaningful regardless of when it's printed.
    flush=True matters here: stdout is line-buffered on a real terminal
    but fully buffered when redirected (e.g. into a log file), so without
    it these lines could sit in the buffer for the whole hang instead of
    appearing when they're printed."""
    prefix = f'[{step}/{total}]'
    print(f'[INFO] {prefix} importing {label}...', flush=True)
    t0 = time.time()
    yield
    print(f'[INFO] {prefix} ...{label} imported ({time.time() - t0:.1f}s)', flush=True)
