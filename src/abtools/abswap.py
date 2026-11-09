import os
from pathlib import Path
import re
import shutil
import sys
import time
import argparse

class AbtoolError(Exception):
    """A problem the user can fix; reported without a traceback."""

def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="abswap", description="Clear a device and copy one audiobook onto it.")
    parser.add_argument("terms", nargs="+", help="search terms, matched in order")
    parser.add_argument("-n", "--dry-run", action="store_true", help="show what would happen; change nothing")
    # parser.add_argument("-i", "--ignore-case", action="store_true", help="case-insensitive matching")
    parser.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    return parser.parse_args(argv)

def get_device():
    devices = os.environ.get('LOAD_AB_DEVICES', '/cygdrive/j/Audible:/cygdrive/k/Audible')
    devices = [Path(p) for p in devices.split(':')]
    devices = [d for d in devices if d.is_dir()]
    
    if len(devices) != 1:
        raise AbtoolError(f"Exactly one device expected, found {len(devices)}: {devices}")
    
    return devices[0]

def get_base():
    return Path(os.environ.get('LOAD_AB_BASE', '~/Audiobooks')).expanduser()

def get_matches(base, terms):
    pattern = re.compile(".*".join(map(re.escape, terms)))
    
    matches = [p for p in base.glob("**/*.*") if pattern.search(str(p.relative_to(base))) and p.is_file()]
    
    if not matches:
        raise AbtoolError("No matches")
    return matches

def get_removals(device):
    return [p for p in device.glob('**/*.*') if p.is_file()]

def check_space(device, matches, to_remove):
    space = shutil.disk_usage(device).free
    space += sum(f.stat().st_size for f in to_remove)
    space -= sum(f.stat().st_size for f in matches)
    if space < 0:
        raise AbtoolError('Not enough free space on device.')
    if space < 10 * 1024 * 1024:
        print(f'WARN: only {space / 1e6:.1f} MB would be free after the copy; it may fail.')

def check_paths(base, device):
    device, base = device.resolve(), base.resolve()
    if device == base or device in base.parents or base in device.parents:
        raise AbtoolError(f"{device} and {base} overlap; refusing to delete.")
    if device.stat().st_dev == base.stat().st_dev:
        raise AbtoolError(f"{device} is on the same filesystem as the library; not a separate device.")

def confirm(prompt="Are you sure?"):
    try:
        return input(f"{prompt} [y/N]: ").strip().lower() in ("y", "yes")
    except (KeyboardInterrupt, EOFError):
        print()
        return False

def do_remove(to_remove):
    for d in to_remove:
        print(f"Removing {d}")
        d.unlink()

CHUNK_SIZE = 1024 * 1024
BAR_WIDTH = 24

def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1000 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1000

def draw_progress(copied, total, elapsed):
    frac = copied / total if total else 1
    filled = int(BAR_WIDTH * frac)
    rate = copied / elapsed if elapsed > 0 else 0
    eta = (total - copied) / rate if rate else 0
    line = (f"[{'#' * filled}{'-' * (BAR_WIDTH - filled)}] {frac:4.0%}  "
            f"{human(copied)}/{human(total)}  {human(rate)}/s  "
            f"ETA {int(eta // 60):02d}:{int(eta % 60):02d}")
    sys.stdout.write("\r" + line.ljust(78))
    sys.stdout.flush()

def copy_with_progress(src, dest, show=None):
    """Copy src to dest in chunks, drawing a progress bar when show is true.

    By default the bar is shown only when stdout is a terminal.
    """
    if show is None:
        show = sys.stdout.isatty()
    total = src.stat().st_size
    copied = 0
    start = last_draw = time.monotonic()
    try:
        with open(src, "rb") as fin, open(dest, "wb") as fout:
            while True:
                chunk = fin.read(CHUNK_SIZE)
                if not chunk:
                    break
                fout.write(chunk)
                copied += len(chunk)
                now = time.monotonic()
                if show and now - last_draw >= 0.1:
                    draw_progress(copied, total, now - start)
                    last_draw = now
            if show:
                draw_progress(copied, total, time.monotonic() - start)
                sys.stdout.write("\nSyncing to device...")
                sys.stdout.flush()
            # Flush to the device so "done" really means done, not "in the OS cache".
            fout.flush()
            os.fsync(fout.fileno())
    finally:
        if show:
            print()

def do_copy(src, device):
    dest = device / src.name
    print(f"Copying {src}")
    try:
        copy_with_progress(src, dest)
        if dest.stat().st_size != src.stat().st_size:
            raise OSError(f"size mismatch: wrote {dest.stat().st_size} of {src.stat().st_size} bytes")
    except BaseException:
        # Also covers Ctrl-C. Remove the partial file, but never let a cleanup
        # failure hide the original error.
        try:
            dest.unlink(missing_ok=True)
        except OSError as cleanup_error:
            print(f"WARN: could not remove partial file {dest}: {cleanup_error}", file=sys.stderr)
        raise
    print("Done.")

def main(argv=None):
    args = parse_args(argv)
    try:
        device = get_device()
        print(f"Device: {device}")
        base = get_base()
        print(f"Searching in {base}")
        check_paths(base, device)
        matches = get_matches(base, args.terms)
        print("Matches:")
        for m in matches:
            print(f"  {m}")
        if len(matches) > 1:
            raise AbtoolError(f"Must match exactly one file, got {len(matches)}")
        to_remove = get_removals(device)
        if to_remove:
            print('To Remove:')
            for p in to_remove:
                print(f"  {p}")
        check_space(device, matches, to_remove)
        if args.dry_run:
            print("Dry run: nothing changed.")
            return 0
        if not (args.yes or confirm()):
            print("Aborted.")
            return 0
        try:
            do_remove(to_remove)
        except OSError as e:
            raise AbtoolError(f"Failed while clearing the device: {e}. "
                              "The device may be partly cleared; nothing was copied.") from e
        try:
            do_copy(matches[0], device)
        except OSError as e:
            raise AbtoolError(f"Copy failed: {e}. The device was cleared, "
                              "and the audiobook was not copied.") from e
    except AbtoolError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())

