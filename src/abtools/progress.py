"""A small terminal progress bar for byte transfers.

ProgressBar is callable as ``bar(done, total)``, so it can be passed anywhere
a progress callback is accepted. It knows nothing about files or copying.
"""
import sys
import time

BAR_WIDTH = 24
LINE_WIDTH = 78


def human(n):
    """Format a byte count, e.g. 1500 -> '1.5 KB'."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1000 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1000


def format_line(done, total, elapsed):
    """Render one progress line (without the carriage return or padding)."""
    frac = done / total if total else 1
    filled = int(BAR_WIDTH * frac)
    rate = done / elapsed if elapsed > 0 else 0
    eta = (total - done) / rate if rate else 0
    return (f"[{'#' * filled}{'-' * (BAR_WIDTH - filled)}] {frac:4.0%}  "
            f"{human(done)}/{human(total)}  {human(rate)}/s  "
            f"ETA {int(eta // 60):02d}:{int(eta % 60):02d}")


class ProgressBar:
    """Draws a redrawing one-line bar; throttled, but always draws completion.

    The stream defaults to sys.stdout, looked up at write time. Call close()
    when finished (including after an error) so the cursor ends up on a fresh
    line.
    """

    def __init__(self, stream=None, interval=0.1, clock=time.monotonic):
        self._stream = stream
        self._interval = interval
        self._clock = clock
        self._start = None
        self._last_draw = None
        self._line_open = False

    def __call__(self, done, total):
        now = self._clock()
        if self._start is None:
            self._start = now
        finished = done >= total
        if not finished and self._last_draw is not None and now - self._last_draw < self._interval:
            return
        self._last_draw = now
        self._write("\r" + format_line(done, total, now - self._start).ljust(LINE_WIDTH))

    def status(self, text):
        """Print a status message on the line below the bar."""
        self._write("\n" + text)

    def close(self):
        """End the current line if anything is on it. Safe to call repeatedly."""
        if self._line_open:
            self._write("\n")
            self._line_open = False

    def _write(self, text):
        stream = self._stream if self._stream is not None else sys.stdout
        stream.write(text)
        stream.flush()
        self._line_open = not text.endswith("\n")
