import os
from pathlib import Path
import re
import shutil
import sys
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

def do_copy(src, device):
    print(f"Copying {src}")
    shutil.copy(src, device)
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
        do_remove(to_remove)
        do_copy(matches[0], device)
    except AbtoolError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())

