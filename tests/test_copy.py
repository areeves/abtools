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


# --- human / draw_progress ------------------------------------------------

def test_human_units():
    assert [abswap.human(n) for n in (999, 1500, 2_500_000, 3_200_000_000)] == [
        "999 B", "1.5 KB", "2.5 MB", "3.2 GB"]


def test_draw_progress_half_filled(capsys):
    abswap.draw_progress(50, 100, 5.0)
    out = capsys.readouterr().out
    assert "[" + "#" * 12 + "-" * 12 + "]  50%" in out
    assert out.startswith("\r")


def test_draw_progress_zero_byte_file_does_not_crash(capsys):
    abswap.draw_progress(0, 0, 0.0)
    assert "100%" in capsys.readouterr().out


def test_draw_progress_fits_in_78_columns(capsys):
    abswap.draw_progress(3_200_000_000, 3_200_000_000, 1.0)
    for segment in capsys.readouterr().out.split("\r"):
        assert len(segment) <= 78


# --- copy_with_progress ---------------------------------------------------

def test_copy_is_byte_identical(src, dev):
    abswap.copy_with_progress(src, dev / src.name, show=False)
    assert (dev / src.name).read_bytes() == src.read_bytes()


def test_copy_empty_file(tmp_path, dev):
    empty = tmp_path / "empty.m4b"
    empty.write_bytes(b"")
    abswap.copy_with_progress(empty, dev / "empty.m4b", show=True)
    assert (dev / "empty.m4b").read_bytes() == b""


def test_copy_silent_when_not_a_terminal(src, dev, capsys):
    # Under pytest stdout is captured, so isatty() is False: the default is silent.
    abswap.copy_with_progress(src, dev / src.name)
    assert capsys.readouterr().out == ""


def test_copy_shows_bar_when_asked(monkeypatch, src, dev, capsys):
    monkeypatch.setattr(abswap, "CHUNK_SIZE", 64 * 1024)
    ticks = iter(i * 0.2 for i in range(10_000))  # every clock read is 0.2 s later
    monkeypatch.setattr(abswap.time, "monotonic", lambda: next(ticks))
    abswap.copy_with_progress(src, dev / src.name, show=True)
    out = capsys.readouterr().out
    assert out.count("\r") > 5
    assert "100%" in out
    assert "Syncing to device..." in out
    assert out.endswith("\n")


def test_copy_fsyncs_before_returning(monkeypatch, src, dev):
    calls = []
    real_fsync = abswap.os.fsync
    monkeypatch.setattr(abswap.os, "fsync", lambda fd: (calls.append(fd), real_fsync(fd))[1])
    abswap.copy_with_progress(src, dev / src.name, show=False)
    assert len(calls) == 1


def test_bar_line_is_terminated_if_sync_fails(monkeypatch, src, dev, capsys):
    def boom(fd):
        raise OSError("device removed")
    monkeypatch.setattr(abswap.os, "fsync", boom)
    with pytest.raises(OSError):
        abswap.copy_with_progress(src, dev / src.name, show=True)
    assert capsys.readouterr().out.endswith("\n")


# --- do_copy: cleanup and verification -----------------------------------

def test_do_copy_success(src, dev, capsys):
    abswap.do_copy(src, dev)
    assert (dev / src.name).read_bytes() == src.read_bytes()
    assert "Done." in capsys.readouterr().out


def failing_copy(exc):
    """A copy that writes some bytes and then fails, like a full disk."""
    def copy(src, dest, show=None):
        dest.write_bytes(b"partial")
        raise exc
    return copy


def test_do_copy_removes_partial_file_and_reraises(monkeypatch, src, dev):
    monkeypatch.setattr(abswap, "copy_with_progress", failing_copy(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        abswap.do_copy(src, dev)
    assert list(dev.iterdir()) == []


def test_do_copy_removes_partial_file_on_ctrl_c(monkeypatch, src, dev):
    monkeypatch.setattr(abswap, "copy_with_progress", failing_copy(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        abswap.do_copy(src, dev)
    assert list(dev.iterdir()) == []


def test_do_copy_detects_short_copy(monkeypatch, src, dev):
    def short_copy(s, dest, show=None):
        dest.write_bytes(b"short")
    monkeypatch.setattr(abswap, "copy_with_progress", short_copy)
    with pytest.raises(OSError, match="size mismatch"):
        abswap.do_copy(src, dev)
    assert list(dev.iterdir()) == []


def test_cleanup_failure_does_not_mask_original_error(monkeypatch, src, dev, capsys):
    monkeypatch.setattr(abswap, "copy_with_progress", failing_copy(OSError("disk full")))
    real_unlink = abswap.Path.unlink

    def stuck_unlink(self, missing_ok=False):
        if self.name == src.name:
            raise OSError("busy")
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(abswap.Path, "unlink", stuck_unlink)
    with pytest.raises(OSError, match="disk full"):  # the original, not "busy"
        abswap.do_copy(src, dev)
    assert "could not remove partial file" in capsys.readouterr().err
