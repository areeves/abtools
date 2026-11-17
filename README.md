# abtools

Tools for managing audiobooks on portable devices.

## Install

```
pip install git+https://github.com/areeves/abtools.git
```

Or, from a local clone (editable, handy for development):

```
pip install -e .
```

Requires Python 3.8 or newer. There are no third-party dependencies.

## abswap

Clears a portable device and copies one audiobook onto it.

```
abswap TERM [TERM ...]
```

`abswap` will:

1. Find the connected device (exactly one device root must be present) and
   check that it has all the folders listed under
   [Device folders](#device-folders). abswap never creates them: a missing
   folder means something is wrong with the device, so it stops.
2. Search your audiobook library for files whose path matches the search terms.
   Terms are matched in order and case-sensitively, so `abswap Dune Messiah`
   matches `Dune/Dune Messiah.m4b` but not a path where "Messiah" comes before
   "Dune". The match runs against the path relative to the library root; terms
   are escaped, not treated as regular expressions.
3. Require exactly one matching file. If the same book exists in several
   formats, add a search term (such as the extension) to pick one.
4. Choose the destination folder from the file's extension, list every file
   currently in the device folders, and check there is enough free space for
   the copy once those files are removed.
5. Ask for confirmation (`[y/N]`).
6. Delete every file in the device folders, then copy the audiobook into its
   folder (as a single file, without its library subdirectories). When run in
   a terminal, a progress bar shows percentage, size, speed and time remaining;
   the copy is flushed to the device before `Done.` is printed.

> **Warning:** `abswap` deletes *all* files found anywhere inside each device
> folder (recursively), not just old audiobooks, in every folder listed below,
> whichever format you are copying. The folders themselves, and anything else on
> the device, are left alone.

### Device folders

Each format lives in its own folder on the device:

| Folder | Extensions |
| --- | --- |
| `Audible/` | `.aax` |
| `Audiobooks/` | `.mp3`, `.m4a`, `.m4b` |

Extensions are matched without regard to case. A file with any other extension
is rejected before anything on the device is touched. The mapping is the
`SUBFOLDERS` constant in `src/abtools/abswap.py`.

### Configuration

Both settings are environment variables.

| Variable | Default | Meaning |
| --- | --- | --- |
| `LOAD_AB_DEVICES` | `/cygdrive/j:/cygdrive/k` | Colon-separated list of candidate device **roots** (the folder that contains `Audible/` and `Audiobooks/`). A root counts as a connected device only if at least one of those folders exists on it, and exactly one must remain. |
| `LOAD_AB_BASE` | `~/Audiobooks` | Root of your audiobook library, searched recursively. |

> **Upgrading:** `LOAD_AB_DEVICES` used to point at the `Audible` folder itself
> (for example `/cygdrive/j/Audible`). It now takes the device root, and an
> entry ending in `Audible` or `Audiobooks` is rejected with an error.

The defaults use Cygwin-style drive paths, so on other systems you will want to
set `LOAD_AB_DEVICES`, for example:

```
export LOAD_AB_DEVICES=/media/me/PLAYER
export LOAD_AB_BASE=~/Audiobooks
abswap Project Hail Mary
```

### Exit behavior

`abswap` exits with status 1 if there is no search term, no match, more than one
match, an unsupported file type, not exactly one device, a missing device
folder, or not enough free space. Answering anything other than `y` or `yes` at
the prompt aborts without touching the device.

## Development

Install the test dependency and run the suite:

```
pip install -e ".[test]"
pytest
```

The tests use temporary directories only and never touch a real device or
your audiobook library. They don't need a second physical filesystem: the
same-filesystem guard is stubbed in the end-to-end tests and tested on its
own with a faked `st_dev`.

## License

MIT. See [LICENSE](LICENSE).
