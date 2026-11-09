import pytest

from abtools import abswap


@pytest.fixture
def library(tmp_path):
    """A library directory containing one audiobook, Dune/Dune.m4b."""
    lib = tmp_path / "library"
    (lib / "Dune").mkdir(parents=True)
    (lib / "Dune" / "Dune.m4b").write_bytes(b"d" * 5000)
    return lib


@pytest.fixture
def device(tmp_path):
    """A device directory holding one old file that abswap should clear."""
    dev = tmp_path / "device"
    dev.mkdir()
    (dev / "old.mp3").write_bytes(b"o" * 100)
    return dev


@pytest.fixture
def env(monkeypatch, library, device):
    """Point abswap at the temp library and device.

    Everything here lives on one filesystem, so the same-filesystem guard in
    check_paths is stubbed out. It has its own dedicated tests, and this keeps
    the suite runnable on any OS without needing a second real filesystem.
    """
    monkeypatch.setenv("LOAD_AB_BASE", str(library))
    monkeypatch.setenv("LOAD_AB_DEVICES", str(device))
    monkeypatch.setattr(abswap, "check_paths", lambda base, device: None)
    return library, device
