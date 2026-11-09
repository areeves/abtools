"""End-to-end tests: call main() the way the console script does."""
import pytest

from abtools import abswap

BOOK = "Dune/Dune.m4b"


def on_device(device):
    return sorted(p.name for p in device.iterdir())


def test_success_replaces_device_contents(env, capsys):
    library, device = env
    assert abswap.main(["-y", "Dune"]) == 0
    assert on_device(device) == ["Dune.m4b"]
    assert (device / "Dune.m4b").read_bytes() == (library / BOOK).read_bytes()
    assert "Done." in capsys.readouterr().out


def test_dry_run_changes_nothing(env, capsys):
    _, device = env
    assert abswap.main(["-n", "Dune"]) == 0
    assert on_device(device) == ["old.mp3"]
    out = capsys.readouterr().out
    assert "To Remove:" in out and "old.mp3" in out
    assert "Dry run" in out


def test_answering_no_aborts_without_touching_device(env, monkeypatch, capsys):
    _, device = env
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert abswap.main(["Dune"]) == 0
    assert on_device(device) == ["old.mp3"]
    assert "Aborted." in capsys.readouterr().out


def test_answering_yes_proceeds(env, monkeypatch):
    _, device = env
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    assert abswap.main(["Dune"]) == 0
    assert on_device(device) == ["Dune.m4b"]


def test_no_match_is_an_error(env, capsys):
    _, device = env
    assert abswap.main(["-y", "Nothing"]) == 1
    assert "No matches" in capsys.readouterr().err
    assert on_device(device) == ["old.mp3"]


def test_multiple_matches_is_an_error_and_lists_them(env, capsys):
    library, device = env
    (library / "Dune" / "Dune2.m4b").write_bytes(b"x")
    assert abswap.main(["-y", "Dune"]) == 1
    captured = capsys.readouterr()
    assert "exactly one file, got 2" in captured.err
    assert "Dune2.m4b" in captured.out and "Dune.m4b" in captured.out
    assert on_device(device) == ["old.mp3"]


def test_no_device_is_an_error(env, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("LOAD_AB_DEVICES", str(tmp_path / "unplugged"))
    assert abswap.main(["-y", "Dune"]) == 1
    assert "Exactly one device" in capsys.readouterr().err


def test_not_enough_space_is_an_error_and_changes_nothing(env, monkeypatch, capsys):
    _, device = env
    monkeypatch.setattr(abswap.shutil, "disk_usage",
                        lambda p: type("U", (), {"free": 0})())
    assert abswap.main(["-y", "Dune"]) == 1
    assert "Not enough free space" in capsys.readouterr().err
    assert on_device(device) == ["old.mp3"]


def test_missing_search_term_is_a_usage_error():
    with pytest.raises(SystemExit) as exc:
        abswap.main([])
    assert exc.value.code == 2


# --- failure reporting ----------------------------------------------------

def test_copy_failure_is_reported_and_leaves_no_partial_file(env, monkeypatch, capsys):
    _, device = env

    def failing(src, dest, show=None):
        dest.write_bytes(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(abswap, "copy_with_progress", failing)
    assert abswap.main(["-y", "Dune"]) == 1
    err = capsys.readouterr().err
    assert "Copy failed: disk full" in err
    assert "device was cleared" in err
    assert on_device(device) == []


def test_delete_failure_is_reported_and_nothing_is_copied(env, monkeypatch, capsys):
    _, device = env
    real_unlink = abswap.Path.unlink

    def read_only(self, missing_ok=False):
        if self.name == "old.mp3":
            raise PermissionError("read-only")
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(abswap.Path, "unlink", read_only)
    assert abswap.main(["-y", "Dune"]) == 1
    err = capsys.readouterr().err
    assert "Failed while clearing the device" in err
    assert "nothing was copied" in err
    assert "Dune.m4b" not in on_device(device)


# --- the safety guard is actually wired into main -------------------------

def test_main_refuses_a_device_that_contains_the_library(library, monkeypatch, capsys):
    """Uses the real check_paths (no `env` fixture): the overlap check needs no
    second filesystem, so it works anywhere."""
    monkeypatch.setenv("LOAD_AB_BASE", str(library))
    monkeypatch.setenv("LOAD_AB_DEVICES", str(library.parent))  # contains the library
    assert abswap.main(["-y", "Dune"]) == 1
    assert "overlap" in capsys.readouterr().err
    assert (library / BOOK).exists()
