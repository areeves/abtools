"""Tests for copying, the progress bar, and failure cleanup."""
import pytest

from abtools import abswap


@pytest.fixture
def src(tmp_path):
    f = tmp_path / "Book.m4b"
    f.write_bytes(bytes(range(256)) * 4096)  # 1 MiB, non-uniform content
    return f


@pytest.fixture
def dev(tmp_path):
    d = tmp_path / "device"
    d.mkdir()
    return d


# --- copy_file ------------------------------------------------------------

def test_copy_is_byte_identical(src, dev):
    abswap.copy_file(src, dev / src.name)
    assert (dev / src.name).read_bytes() == src.read_bytes()


def test_copy_empty_file(tmp_path, dev):
    empty = tmp_path / "empty.m4b"
    empty.write_bytes(b"")
    abswap.copy_file(empty, dev / "empty.m4b")
    assert (dev / "empty.m4b").read_bytes() == b""


def test_copy_needs_no_callbacks(src, dev, capsys):
    abswap.copy_file(src, dev / src.name)
    assert capsys.readouterr().out == ""  # copying itself never prints


def test_progress_callback_sequence(src, dev):
    calls = []
    total = src.stat().st_size
    abswap.copy_file(src, dev / src.name, on_progress=lambda c, t: calls.append((c, t)),
                     chunk_size=256 * 1024)
    assert calls[0] == (0, total)                      # before the first chunk
    assert calls[-1] == (total, total)                 # ends exactly complete
    assert [t for _, t in calls] == [total] * len(calls)
    copied = [c for c, _ in calls]
    assert copied == sorted(copied) and len(set(copied)) == len(copied)  # strictly increasing
    assert len(calls) == 1 + total // (256 * 1024)     # start + one per chunk


def test_progress_callback_for_empty_file(tmp_path, dev):
    empty = tmp_path / "empty.m4b"
    empty.write_bytes(b"")
    calls = []
    abswap.copy_file(empty, dev / "empty.m4b", on_progress=lambda c, t: calls.append((c, t)))
    assert calls == [(0, 0)]


def test_on_sync_runs_once_after_all_progress_and_before_fsync(monkeypatch, src, dev):
    events = []
    real_fsync = abswap.os.fsync

    def fsync(fd):
        events.append("fsync")
        real_fsync(fd)

    monkeypatch.setattr(abswap.os, "fsync", fsync)
    abswap.copy_file(src, dev / src.name,
                     on_progress=lambda c, t: events.append("progress"),
                     on_sync=lambda: events.append("sync"),
                     chunk_size=512 * 1024)
    assert events[-2:] == ["sync", "fsync"]
    assert events.count("sync") == 1 and events.count("fsync") == 1


def test_copy_fsyncs_before_returning(monkeypatch, src, dev):
    calls = []
    real_fsync = abswap.os.fsync
    monkeypatch.setattr(abswap.os, "fsync", lambda fd: (calls.append(fd), real_fsync(fd))[1])
    abswap.copy_file(src, dev / src.name)
    assert len(calls) == 1


def test_errors_from_callbacks_propagate(src, dev):
    def boom(copied, total):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        abswap.copy_file(src, dev / src.name, on_progress=boom)


# --- do_copy: cleanup and verification -----------------------------------

def test_do_copy_success(src, dev, capsys):
    abswap.do_copy(src, dev)
    assert (dev / src.name).read_bytes() == src.read_bytes()
    assert "Done." in capsys.readouterr().out


def failing_copy(exc):
    """A copy that writes some bytes and then fails, like a full disk."""
    def copy(src, dest, **kwargs):
        dest.write_bytes(b"partial")
        raise exc
    return copy


def test_do_copy_removes_partial_file_and_reraises(monkeypatch, src, dev):
    monkeypatch.setattr(abswap, "copy_file", failing_copy(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        abswap.do_copy(src, dev)
    assert list(dev.iterdir()) == []


def test_do_copy_removes_partial_file_on_ctrl_c(monkeypatch, src, dev):
    monkeypatch.setattr(abswap, "copy_file", failing_copy(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        abswap.do_copy(src, dev)
    assert list(dev.iterdir()) == []


def test_do_copy_detects_short_copy(monkeypatch, src, dev):
    def short_copy(s, dest, **kwargs):
        dest.write_bytes(b"short")
    monkeypatch.setattr(abswap, "copy_file", short_copy)
    with pytest.raises(OSError, match="size mismatch"):
        abswap.do_copy(src, dev)
    assert list(dev.iterdir()) == []


def test_cleanup_failure_does_not_mask_original_error(monkeypatch, src, dev, capsys):
    monkeypatch.setattr(abswap, "copy_file", failing_copy(OSError("disk full")))
    real_unlink = abswap.Path.unlink

    def stuck_unlink(self, missing_ok=False):
        if self.name == src.name:
            raise OSError("busy")
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(abswap.Path, "unlink", stuck_unlink)
    with pytest.raises(OSError, match="disk full"):  # the original, not "busy"
        abswap.do_copy(src, dev)
    assert "could not remove partial file" in capsys.readouterr().err


# --- do_copy and the progress bar ----------------------------------------

class RecordingBar:
    """Stands in for ProgressBar and records how do_copy drives it."""

    def __init__(self):
        self.events = []

    def __call__(self, done, total):
        self.events.append(("progress", done, total))

    def status(self, text):
        self.events.append(("status", text))

    def close(self):
        self.events.append(("close",))


def test_do_copy_drives_the_bar_and_closes_it(src, dev):
    bar = RecordingBar()
    abswap.do_copy(src, dev, progress=bar)
    kinds = [e[0] for e in bar.events]
    assert kinds[0] == "progress" and kinds[-1] == "close"
    assert ("status", "Syncing to device...") in bar.events
    assert kinds.index("status") > max(i for i, k in enumerate(kinds) if k == "progress")
    assert kinds.count("close") == 1


def test_do_copy_closes_the_bar_when_the_copy_fails(monkeypatch, src, dev):
    bar = RecordingBar()
    monkeypatch.setattr(abswap, "copy_file", failing_copy(OSError("disk full")))
    with pytest.raises(OSError):
        abswap.do_copy(src, dev, progress=bar)
    assert bar.events == [("close",)]


def test_do_copy_closes_the_bar_on_ctrl_c(monkeypatch, src, dev):
    bar = RecordingBar()
    monkeypatch.setattr(abswap, "copy_file", failing_copy(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        abswap.do_copy(src, dev, progress=bar)
    assert ("close",) in bar.events


def test_do_copy_with_a_real_bar_ends_on_a_fresh_line(src, dev, capsys):
    from abtools.progress import ProgressBar
    abswap.do_copy(src, dev, progress=ProgressBar())
    out = capsys.readouterr().out
    assert "100%" in out
    assert "Syncing to device...\nDone." in out


def test_do_copy_without_a_bar_prints_no_control_characters(src, dev, capsys):
    abswap.do_copy(src, dev)
    out = capsys.readouterr().out
    assert "\r" not in out
    assert out.splitlines() == [f"Copying {src}", "Done."]
