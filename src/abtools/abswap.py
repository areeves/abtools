import os
from pathlib import Path
import re
import shutil
import sys

class AbtoolError(Exception):
    """A problem the user can fix; reported without a traceback."""

def get_device():
    devices = os.environ.get('LOAD_AB_DEVICES', '/cygdrive/j/Audible:/cygdrive/k/Audible')
    devices = [Path(p) for p in devices.split(':')]
    devices = [d for d in devices if d.is_dir()]
    
    if len(devices) != 1:
        raise AbtoolError(f"Exactly one device expected, found {len(devices)}: {devices}")
    
    return devices[0]

def get_base():
    return Path(os.environ.get('LOAD_AB_BASE', '~/Audiobooks')).expanduser()

def get_terms():
    terms = sys.argv[1:]
    if not terms:
        raise AbtoolError('At least one search term argument is required.')
    return terms

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

def main():
    try:
        device = get_device()
        print(f"Device: {device}")
        base = get_base()
        print(f"Searching in {base}")
        terms = get_terms()
        print(f"Search terms: {terms}")
        matches = get_matches(base, terms)
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
        if not confirm():
            print('Aborted.')
            return 0
        do_remove(to_remove)
        do_copy(matches[0], device)
    except AbtoolError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())

