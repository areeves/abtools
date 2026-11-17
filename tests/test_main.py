"""End-to-end tests: call main() the way the console script does."""
import shutil

import pytest

from abtools import abswap

BOOK = "Dune/Dune.m4b"


def on_device(device):
    """Every file on the device, as sorted paths relative to its root."""
    return sorted(p.relative_to(device).as_posix() for p in device.rglob("*") if p.is_file())


def test_success_replaces_device_contents(env, capsys):
    library, device = env
    assert abswap.main(["-y", "Dune"]) == 0
    assert on_device(device) == ["Audiobooks/Dune.m4b"]
    assert (device / "Audiobooks" / "Dune.m4b").read_bytes() == (library / BOOK).read_bytes()
    assert "Done." in capsys.readouterr().out


def test_dry_run_changes_nothing(env, capsys):
    _, device = env
    assert abswap.main(["-n", "Dune"]) == 0
    assert on_device(device) == ["Audiobooks/old.mp3"]
    out = capsys.readouterr().out
    assert "To Remove:" in out and "old.mp3" in out
    assert f"Destination: {device / 'Audiobooks'}" in out
    assert "Dry run" in out


def test_answering_no_aborts_without_touching_device(env, monkeypatch, capsys):
    _, device = env
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert abswap.main(["Dune"]) == 0
    assert on_device(device) == ["Audiobooks/old.mp3"]
    assert "Aborted." in capsys.readouterr().out


def test_answering_yes_proceeds(env, monkeypatch):
    _, device = env
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    assert abswap.main(["Dune"]) == 0
    assert on_device(device) == ["Audiobooks/Dune.m4b"]


def test_no_match_is_an_error(env, capsys):
    _, device = env
    assert abswap.main(["-y", "Nothing"]) == 1
    assert "No matches" in capsys.readouterr().err
    assert on_device(device) == ["Audiobooks/old.mp3"]


def test_multiple_matches_is_an_error_and_lists_them(env, capsys):
    library, device = env
    (library / "Dune" / "Dune2.m4b").write_bytes(b"x")
    assert abswap.main(["-y", "Dune"]) == 1
    captured = capsys.readouterr()
    assert "exactly one file, got 2" in captured.err
    assert "Dune2.m4b" in captured.out and "Dune.m4b" in captured.out
    assert on_device(device) == ["Audiobooks/old.mp3"]


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
    assert on_device(device) == ["Audiobooks/old.mp3"]


def test_missing_search_term_is_a_usage_error():
    with pytest.raises(SystemExit) as exc:
        abswap.main([])
    assert exc.value.code == 2


# --- formats and folders --------------------------------------------------

def test_aax_goes_to_the_audible_folder(env):
    library, device = env
    (library / "Hyperion.aax").write_bytes(b"h" * 300)
    assert abswap.main(["-y", "Hyperion"]) == 0
    assert on_device(device) == ["Audible/Hyperion.aax"]
    assert (device / "Audible" / "Hyperion.aax").read_bytes() == b"h" * 300


@pytest.mark.parametrize("name", ["Song.mp3", "Song.m4a", "Song.M4B"])
def test_other_formats_go_to_the_audiobooks_folder(env, name):
    library, device = env
    (library / name).write_bytes(b"s" * 300)
    assert abswap.main(["-y", "Song"]) == 0
    assert on_device(device) == [f"Audiobooks/{name}"]


def test_book_is_copied_flat_not_into_its_library_subfolders(env):
    _, device = env
    assert abswap.main(["-y", "Dune"]) == 0
    assert not (device / "Audiobooks" / "Dune").exists()
    assert (device / "Audiobooks" / "Dune.m4b").is_file()


def test_clears_every_configured_folder_but_nothing_else(env):
    _, device = env
    (device / "Audible" / "old.aax").write_bytes(b"a")
    (device / "Audiobooks" / "sub").mkdir()
    (device / "Audiobooks" / "sub" / "nested.mp3").write_bytes(b"n")
    (device / "keep.txt").write_bytes(b"k")
    (device / "Other").mkdir()
    (device / "Other" / "keep2.txt").write_bytes(b"k")

    assert abswap.main(["-y", "Dune"]) == 0

    assert on_device(device) == ["Audiobooks/Dune.m4b", "Other/keep2.txt", "keep.txt"]
    # The folders themselves are never removed.
    assert (device / "Audible").is_dir()
    assert (device / "Audiobooks").is_dir()
    assert (device / "Audiobooks" / "sub").is_dir()


def test_unsupported_extension_is_an_error_and_changes_nothing(env, capsys):
    library, device = env
    (library / "Cover.jpg").write_bytes(b"j")
    assert abswap.main(["-y", "Cover"]) == 1
    assert "Unsupported file type .jpg" in capsys.readouterr().err
    assert on_device(device) == ["Audiobooks/old.mp3"]


@pytest.mark.parametrize("missing", list(abswap.SUBFOLDERS))
def test_missing_folder_is_an_error_and_nothing_is_created_or_removed(env, capsys, missing):
    library, device = env
    shutil.rmtree(device / missing)
    before = on_device(device)
    assert abswap.main(["-y", "Dune"]) == 1
    err = capsys.readouterr().err
    assert "missing" in err and missing in err
    assert not (device / missing).exists()
    assert on_device(device) == before
    assert (library / BOOK).exists()


def test_old_style_device_path_is_rejected_with_a_helpful_message(env, monkeypatch, capsys):
    _, device = env
    monkeypatch.setenv("LOAD_AB_DEVICES", str(device / "Audible"))
    assert abswap.main(["-y", "Dune"]) == 1
    assert "device root" in capsys.readouterr().err
    assert on_device(device) == ["Audiobooks/old.mp3"]


# --- failure reporting ----------------------------------------------------

def test_copy_failure_is_reported_and_leaves_no_partial_file(env, monkeypatch, capsys):
    _, device = env

    def failing(src, dest, **kwargs):
        dest.write_bytes(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(abswap, "copy_file", failing)
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
    assert "Audiobooks/Dune.m4b" not in on_device(device)


# --- the safety guard is actually wired into main -------------------------

def test_main_refuses_a_device_that_contains_the_library(library, monkeypatch, capsys):
    """Uses the real check_paths (no `env` fixture): the overlap check needs no
    second filesystem, so it works anywhere."""
    root = library.parent  # contains the library
    for folder in abswap.SUBFOLDERS:
        (root / folder).mkdir()
    monkeypatch.setenv("LOAD_AB_BASE", str(library))
    monkeypatch.setenv("LOAD_AB_DEVICES", str(root))
    assert abswap.main(["-y", "Dune"]) == 1
    assert "overlap" in capsys.readouterr().err
    assert (library / BOOK).exists()


# --- the bar is only used on a terminal -----------------------------------

@pytest.mark.parametrize("is_tty, expect_bar", [(True, True), (False, False)])
def test_progress_bar_only_when_stdout_is_a_terminal(env, monkeypatch, is_tty, expect_bar):
    seen = []
    real_do_copy = abswap.do_copy

    def spy(src, device, progress=None):
        seen.append(progress)
        return real_do_copy(src, device)   # copy without drawing

    monkeypatch.setattr(abswap, "do_copy", spy)
    monkeypatch.setattr(abswap.sys.stdout, "isatty", lambda: is_tty)
    assert abswap.main(["-y", "Dune"]) == 0
    assert len(seen) == 1
    assert (seen[0] is not None) is expect_bar
