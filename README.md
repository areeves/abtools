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

1. Find the connected device (exactly one device directory must exist).
2. Search your audiobook library for files whose path matches the search terms.
   Terms are matched in order and case-sensitively, so `abswap Dune Messiah`
   matches `Dune/Dune Messiah.m4b` but not a path where "Messiah" comes before
   "Dune". The match runs against the path relative to the library root; terms
   are escaped, not treated as regular expressions.
3. Require exactly one matching file.
4. List every file currently on the device and check there is enough free space
   for the copy once those files are removed.
5. Ask for confirmation (`[y/N]`).
6. Delete every file on the device, then copy the audiobook onto it.

> **Warning:** `abswap` deletes *all* files found anywhere under the device
> directory (recursively), not just old audiobooks. Only point it at a
> directory that holds nothing you want to keep.

### Configuration

Both settings are environment variables.

| Variable | Default | Meaning |
| --- | --- | --- |
| `LOAD_AB_DEVICES` | `/cygdrive/j/Audible:/cygdrive/k/Audible` | Colon-separated list of candidate device directories. Directories that don't exist are ignored, and exactly one must remain. |
| `LOAD_AB_BASE` | `~/Audiobooks` | Root of your audiobook library, searched recursively. |

The defaults use Cygwin-style drive paths, so on other systems you will want to
set `LOAD_AB_DEVICES`, for example:

```
export LOAD_AB_DEVICES=/media/me/PLAYER/Audible
export LOAD_AB_BASE=~/Audiobooks
abswap Project Hail Mary
```

### Exit behavior

`abswap` exits with status 1 if there is no search term, no match, more than one
match, not exactly one device, or not enough free space. Answering anything
other than `y` or `yes` at the prompt aborts without touching the device.

## License

MIT. See [LICENSE](LICENSE).
