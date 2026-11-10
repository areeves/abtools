"""Tests for the progress bar. It knows nothing about files or copying."""
import io

import pytest

from abtools import progress
from abtools.progress import ProgressBar, format_line, human


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def out():
    return io.StringIO()


@pytest.fixture
def bar(out, clock):
    return ProgressBar(stream=out, clock=clock)


def frames(out):
    """The individual redraws written so far (each starts with a carriage return)."""
    return [f for f in out.getvalue().split("\r") if f]


# --- human / format_line --------------------------------------------------

def test_human_units():
    assert [human(n) for n in (0, 999, 1500, 2_500_000, 3_200_000_000)] == [
        "0 B", "999 B", "1.5 KB", "2.5 MB", "3.2 GB"]


def test_human_does_not_go_past_gb():
    assert human(5_000_000_000_000) == "5000.0 GB"


def test_format_line_half_filled_bar():
    line = format_line(50, 100, 5.0)
    assert line.startswith("[" + "#" * 12 + "-" * 12 + "]  50%")
    assert "50 B/100 B" in line
    assert "10 B/s" in line
    assert line.endswith("ETA 00:05")


def test_format_line_eta_formats_minutes_and_seconds():
    # 1 byte/s, 125 bytes left -> 02:05
    assert format_line(1, 126, 1.0).endswith("ETA 02:05")


def test_format_line_zero_byte_total_is_complete():
    line = format_line(0, 0, 0.0)
    assert "100%" in line
    assert "#" * progress.BAR_WIDTH in line


def test_format_line_before_any_time_has_passed():
    assert "0 B/s" in format_line(10, 100, 0.0)  # no division by zero


def test_format_line_fits_the_line_width_in_the_worst_case():
    assert len(format_line(3_200_000_000, 3_200_000_000, 1.0)) <= progress.LINE_WIDTH


# --- drawing --------------------------------------------------------------

def test_draws_in_place_with_carriage_return_and_no_newline(bar, out):
    bar(10, 100)
    text = out.getvalue()
    assert text.startswith("\r")
    assert "\n" not in text


def test_each_frame_is_padded_to_the_full_width(bar, out):
    bar(10, 100)
    assert all(len(f) == progress.LINE_WIDTH for f in frames(out))


def test_redraws_are_throttled(bar, out, clock):
    bar(1, 100)
    clock.advance(0.01)
    bar(2, 100)   # too soon: skipped
    clock.advance(0.01)
    bar(3, 100)   # still too soon: skipped
    assert len(frames(out)) == 1
    clock.advance(0.2)
    bar(4, 100)
    assert len(frames(out)) == 2


def test_completion_is_drawn_even_when_throttled(bar, out, clock):
    bar(1, 100)
    clock.advance(0.001)
    bar(100, 100)
    assert len(frames(out)) == 2
    assert "100%" in frames(out)[-1]


def test_zero_byte_transfer_draws_complete_frame(bar, out):
    bar(0, 0)
    assert "100%" in out.getvalue()


def test_elapsed_time_is_measured_from_the_first_call(bar, out, clock):
    bar(0, 100)
    clock.advance(10.0)
    bar(50, 100)
    # 50 bytes in 10 s -> 5 B/s, 50 left -> 10 s
    assert "5 B/s" in frames(out)[-1]
    assert "ETA 00:10" in frames(out)[-1]


def test_defaults_to_current_stdout(capsys):
    ProgressBar()(10, 100)
    assert "\r[" in capsys.readouterr().out


# --- status / close -------------------------------------------------------

def test_status_goes_on_the_line_below(bar, out):
    bar(100, 100)
    bar.status("Syncing...")
    assert out.getvalue().endswith("\nSyncing...")


def test_close_ends_an_open_line(bar, out):
    bar(10, 100)
    bar.close()
    assert out.getvalue().endswith("\n")


def test_close_after_status_ends_that_line(bar, out):
    bar(100, 100)
    bar.status("Syncing...")
    bar.close()
    assert out.getvalue().endswith("Syncing...\n")


def test_close_writes_nothing_if_nothing_was_drawn(bar, out):
    bar.close()
    assert out.getvalue() == ""


def test_close_is_idempotent(bar, out):
    bar(10, 100)
    bar.close()
    before = out.getvalue()
    bar.close()
    assert out.getvalue() == before
