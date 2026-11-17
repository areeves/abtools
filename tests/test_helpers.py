"""Unit tests for the small helper functions in abswap."""
import os
import types
from pathlib import Path

import pytest

from abtools import abswap
from abtools.abswap import AbtoolError


# --- parse_args -----------------------------------------------------------

def test_parse_args_defaults():
    args = abswap.parse_args(["Dune"])
    assert args.terms == ["Dune"]
    assert args.dry_run is False
    assert args.yes is False


def test_parse_args_flags_and_multiple_terms():
    args = abswap.parse_args(["-n", "-y", "Dune", "Messiah"])
    assert args.terms == ["Dune", "Messiah"]
    assert args.dry_run and args.yes


def test_parse_args_requires_a_term(capsys):
    with pytest.raises(SystemExit) as exc:
        abswap.parse_args([])
    assert exc.value.code == 2
    assert "terms" in capsys.readouterr().err


# --- the folder mapping ---------------------------------------------------

def test_mapping_is_consistent():
    # No extension may be claimed by two folders (the derived lookup would
    # silently keep only one), and extensions are stored lowercase with a dot.
    all_exts = [ext for exts in abswap.SUBFOLDERS.values() for ext in exts]
    assert len(abswap.EXTENSION_SUBFOLDER) == len(all_exts)
    assert all(ext.startswith(".") and ext == ext.lower() for ext in all_exts)


@pytest.mark.parametrize("name, folder", [
    ("Book.aax", "Audible"), ("Book.AAX", "Audible"),
    ("Book.mp3", "Audiobooks"), ("Book.m4a", "Audiobooks"),
    ("Book.m4b", "Audiobooks"), ("Book.M4B", "Audiobooks"),
    ("Dune Messiah (Unabridged).m4b", "Audiobooks"),
])
def test_get_subfolder(name, folder):
    assert abswap.get_subfolder(Path("lib") / name) == folder


@pytest.mark.parametrize("name", ["cover.jpg", "notes.pdf", "README", "Book.aax.bak"])
def test_get_subfolder_rejects_unsupported_files(name):
    with pytest.raises(AbtoolError, match="Unsupported file type"):
        abswap.get_subfolder(Path("lib") / name)


# --- get_device / check_subfolders / get_base -----------------------------

def make_device(path, folders=None):
    """Create a device root containing the given (default: all) folders."""
    path.mkdir(parents=True, exist_ok=True)
    for folder in (abswap.SUBFOLDERS if folders is None else folders):
        (path / folder).mkdir()
    return path


def test_get_device_returns_the_one_existing_device(monkeypatch, tmp_path):
    real = make_device(tmp_path / "real")
    missing = tmp_path / "missing"
    monkeypatch.setenv("LOAD_AB_DEVICES", f"{missing}:{real}")
    assert abswap.get_device() == real


def test_get_device_none_exist(monkeypatch, tmp_path):
    monkeypatch.setenv("LOAD_AB_DEVICES", str(tmp_path / "nope"))
    with pytest.raises(AbtoolError, match="found 0"):
        abswap.get_device()


def test_get_device_more_than_one_exists(monkeypatch, tmp_path):
    a, b = make_device(tmp_path / "a"), make_device(tmp_path / "b")
    monkeypatch.setenv("LOAD_AB_DEVICES", f"{a}:{b}")
    with pytest.raises(AbtoolError, match="found 2"):
        abswap.get_device()


def test_get_device_ignores_a_root_without_any_configured_folder(monkeypatch, tmp_path):
    """A stray drive at one of the paths must not be mistaken for a player."""
    stray = tmp_path / "stray"
    stray.mkdir()
    player = make_device(tmp_path / "player")
    monkeypatch.setenv("LOAD_AB_DEVICES", f"{stray}:{player}")
    assert abswap.get_device() == player


def test_get_device_accepts_a_root_with_only_some_folders(monkeypatch, tmp_path):
    """Partly set-up devices are found here; check_subfolders then rejects them."""
    partial = make_device(tmp_path / "partial", folders=["Audible"])
    monkeypatch.setenv("LOAD_AB_DEVICES", str(partial))
    assert abswap.get_device() == partial


def test_get_device_skips_empty_entries(monkeypatch, tmp_path):
    real = make_device(tmp_path / "real")
    monkeypatch.setenv("LOAD_AB_DEVICES", f":{real}:")
    assert abswap.get_device() == real


@pytest.mark.parametrize("folder", list(abswap.SUBFOLDERS))
def test_get_device_rejects_old_style_subfolder_entries(monkeypatch, tmp_path, folder):
    root = make_device(tmp_path / "root")
    monkeypatch.setenv("LOAD_AB_DEVICES", str(root / folder))
    with pytest.raises(AbtoolError, match="device root"):
        abswap.get_device()


def test_check_subfolders_accepts_a_complete_device(tmp_path):
    abswap.check_subfolders(make_device(tmp_path / "dev"))  # no error


def test_check_subfolders_names_every_missing_folder(tmp_path):
    dev = make_device(tmp_path / "dev", folders=[])
    with pytest.raises(AbtoolError, match="Audible, Audiobooks"):
        abswap.check_subfolders(dev)
    assert list(dev.iterdir()) == []  # never creates them


def test_check_subfolders_rejects_a_file_in_place_of_a_folder(tmp_path):
    dev = make_device(tmp_path / "dev", folders=["Audiobooks"])
    (dev / "Audible").write_bytes(b"not a folder")
    with pytest.raises(AbtoolError, match="Audible"):
        abswap.check_subfolders(dev)


def test_get_base_expands_user(monkeypatch):
    monkeypatch.setenv("LOAD_AB_BASE", "~/Books")
    assert abswap.get_base() == Path("~/Books").expanduser()


# --- get_matches ----------------------------------------------------------

@pytest.fixture
def shelf(tmp_path):
    for rel in ("Dune/Dune Messiah.m4b", "Dune/Dune.m4b", "Messiah/Other.m4b", "A (B).m4b"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    return tmp_path


def names(paths, base):
    return sorted(str(p.relative_to(base)).replace(os.sep, "/") for p in paths)


def test_matches_single_term(shelf):
    assert names(abswap.get_matches(shelf, ["Other"]), shelf) == ["Messiah/Other.m4b"]


def test_matches_terms_must_appear_in_order(shelf):
    # "Dune ... Messiah" matches Dune/Dune Messiah.m4b but not Messiah/Other.m4b,
    # where Messiah comes before anything resembling Dune.
    assert names(abswap.get_matches(shelf, ["Dune", "Messiah"]), shelf) == ["Dune/Dune Messiah.m4b"]
    with pytest.raises(AbtoolError):
        abswap.get_matches(shelf, ["Other", "Messiah"])


def test_matches_are_literal_not_regex(shelf):
    # Unescaped, "(B)" would be a regex group matching just "B".
    assert names(abswap.get_matches(shelf, ["(B)"]), shelf) == ["A (B).m4b"]
    with pytest.raises(AbtoolError):
        abswap.get_matches(shelf, ["D.ne"])


def test_no_matches_raises(shelf):
    with pytest.raises(AbtoolError, match="No matches"):
        abswap.get_matches(shelf, ["Nothing"])


def test_match_is_against_relative_path_only(shelf):
    # The base directory's own name must not make everything match.
    with pytest.raises(AbtoolError):
        abswap.get_matches(shelf, [shelf.name])


# --- get_removals / do_remove --------------------------------------------

def test_removals_include_nested_files_in_every_folder(tmp_path):
    dev = make_device(tmp_path / "dev")
    (dev / "Audiobooks" / "sub").mkdir()
    (dev / "Audiobooks" / "a.mp3").write_bytes(b"1")
    (dev / "Audiobooks" / "sub" / "b.m4b").write_bytes(b"2")
    (dev / "Audible" / "c.aax").write_bytes(b"3")
    assert names(abswap.get_removals(dev), dev) == [
        "Audible/c.aax", "Audiobooks/a.mp3", "Audiobooks/sub/b.m4b"]


def test_removals_never_reach_outside_the_configured_folders(tmp_path):
    dev = make_device(tmp_path / "dev")
    (dev / "Other").mkdir()
    (dev / "Other" / "keep.mp3").write_bytes(b"1")
    (dev / "keep.m4b").write_bytes(b"2")
    (dev / "Audiobooks" / "old.mp3").write_bytes(b"3")
    assert names(abswap.get_removals(dev), dev) == ["Audiobooks/old.mp3"]


def test_removals_include_any_file_not_just_ones_with_extensions(tmp_path):
    dev = make_device(tmp_path / "dev")
    (dev / "Audible" / "notes").write_bytes(b"1")
    (dev / "Audible" / ".hidden").write_bytes(b"2")
    assert names(abswap.get_removals(dev), dev) == ["Audible/.hidden", "Audible/notes"]


def test_removals_ignore_directories(tmp_path):
    dev = make_device(tmp_path / "dev")
    (dev / "Audible" / "empty_dir").mkdir()
    assert abswap.get_removals(dev) == []


def test_do_remove_deletes_files(tmp_path, capsys):
    f = tmp_path / "a.mp3"
    f.write_bytes(b"1")
    abswap.do_remove([f])
    assert not f.exists()
    assert "Removing" in capsys.readouterr().out


# --- check_space ----------------------------------------------------------

def fake_usage(free):
    return lambda path: types.SimpleNamespace(total=0, used=0, free=free)


def test_check_space_ok(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(abswap.shutil, "disk_usage", fake_usage(100 * 1024 * 1024))
    src = tmp_path / "s.m4b"
    src.write_bytes(b"x" * 1000)
    abswap.check_space(tmp_path, [src], [])
    assert capsys.readouterr().out == ""


def test_check_space_not_enough(monkeypatch, tmp_path):
    monkeypatch.setattr(abswap.shutil, "disk_usage", fake_usage(500))
    src = tmp_path / "s.m4b"
    src.write_bytes(b"x" * 1000)
    with pytest.raises(AbtoolError, match="Not enough free space"):
        abswap.check_space(tmp_path, [src], [])


def test_check_space_counts_files_about_to_be_removed(monkeypatch, tmp_path):
    monkeypatch.setattr(abswap.shutil, "disk_usage", fake_usage(500))
    src = tmp_path / "s.m4b"
    src.write_bytes(b"x" * 1000)
    old = tmp_path / "old.mp3"
    old.write_bytes(b"x" * 600)
    abswap.check_space(tmp_path, [src], [old])  # 500 + 600 - 1000 >= 0: no error


def test_check_space_warns_when_nearly_full(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(abswap.shutil, "disk_usage", fake_usage(2000))
    src = tmp_path / "s.m4b"
    src.write_bytes(b"x" * 1000)
    abswap.check_space(tmp_path, [src], [])
    assert "WARN" in capsys.readouterr().out


# --- check_paths ----------------------------------------------------------

@pytest.fixture
def two_dirs(tmp_path):
    base, dev = tmp_path / "base", tmp_path / "dev"
    base.mkdir()
    dev.mkdir()
    return base, dev


def test_check_paths_rejects_identical(two_dirs):
    base, _ = two_dirs
    with pytest.raises(AbtoolError, match="overlap"):
        abswap.check_paths(base, base)


def test_check_paths_rejects_device_inside_library(two_dirs):
    base, _ = two_dirs
    inner = base / "usb"
    inner.mkdir()
    with pytest.raises(AbtoolError, match="overlap"):
        abswap.check_paths(base, inner)


def test_check_paths_rejects_device_containing_library(two_dirs):
    base, dev = two_dirs
    with pytest.raises(AbtoolError, match="overlap"):
        abswap.check_paths(base, base.parent)


def test_check_paths_rejects_symlink_into_library(two_dirs):
    base, dev = two_dirs
    link = dev / "link"
    try:
        link.symlink_to(base, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported here")
    with pytest.raises(AbtoolError, match="overlap"):
        abswap.check_paths(base, link)


def patch_dev_ids(monkeypatch, ids):
    """Make Path.stat report a chosen st_dev for specific directories."""
    real_stat = Path.stat

    def fake_stat(self, *args, **kwargs):
        if self in ids:
            return types.SimpleNamespace(st_dev=ids[self])
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", fake_stat)


def test_check_paths_rejects_same_filesystem(monkeypatch, two_dirs):
    base, dev = two_dirs
    patch_dev_ids(monkeypatch, {base.resolve(): 7, dev.resolve(): 7})
    with pytest.raises(AbtoolError, match="same filesystem"):
        abswap.check_paths(base, dev)


def test_check_paths_accepts_separate_filesystems(monkeypatch, two_dirs):
    base, dev = two_dirs
    patch_dev_ids(monkeypatch, {base.resolve(): 7, dev.resolve(): 8})
    abswap.check_paths(base, dev)  # no error


# --- confirm --------------------------------------------------------------

@pytest.mark.parametrize("answer, expected", [
    ("y", True), ("Y", True), ("yes", True), (" YES ", True),
    ("n", False), ("", False), ("maybe", False), ("yep", False),
])
def test_confirm_answers(monkeypatch, answer, expected):
    monkeypatch.setattr("builtins.input", lambda prompt="": answer)
    assert abswap.confirm() is expected


@pytest.mark.parametrize("exc", [EOFError, KeyboardInterrupt])
def test_confirm_treats_interrupt_and_eof_as_no(monkeypatch, exc):
    def raiser(prompt=""):
        raise exc
    monkeypatch.setattr("builtins.input", raiser)
    assert abswap.confirm() is False
