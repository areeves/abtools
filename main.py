import os
from pathlib import Path
import re
import shutil
import sys

devices = os.environ.get('LOAD_AB_DEVICES', '/cygdrive/j/Audible:/cygdrive/k/Audible')
devices = [Path(p) for p in devices.split(':')]
devices = [d for d in devices if d.is_dir()]

if len(devices) != 1:
    print(f"Exactly one device expected, found {len(devices)}: {devices}")
    sys.exit(1)

device = devices[0]
print(f"Device: {device}")

base = Path(os.environ.get('LOAD_AB_BASE', '~/Audiobooks')).expanduser()
print(f"Searching in {base}")

terms = sys.argv[1:]
if not terms:
    print('At least one search term argument is required.')
    sys.exit(1)
print(f"Search terms: {terms}")

pattern = re.compile(".*".join(map(re.escape, terms)))

matches = [p for p in base.glob("**/*.*") if pattern.search(str(p.relative_to(base))) and p.is_file()]

if not matches:
    print("No matches")
    sys.exit(1)
print("Matches:")
for m in matches:
    print(f"  {m}")
if len(matches) > 1:
    print(f"Must match exactly one file, got {len(matches)}")
    sys.exit(1)

to_remove = [p for p in device.glob('**/*.*') if p.is_file()]
if to_remove:
    print('To Remove:')
    for p in to_remove:
        print(f"  {p}")

space = shutil.disk_usage(device).free
space += sum(f.stat().st_size for f in to_remove)
space -= sum(f.stat().st_size for f in matches)
if space < 0:
    print('Not enough free space on device.')
    sys.exit(1)
if space < 10 * 1024 * 1024:
    print(f'WARN: only {space / 1e6:.1f} MB would be free after the copy; it may fail.')

def confirm(prompt="Are you sure?"):
    try:
        return input(f"{prompt} [y/N]: ").strip().lower() in ("y", "yes")
    except (KeyboardInterrupt, EOFError):
        print()
        return False
if not confirm():
    print('Aborted.')
    sys.exit(0)

for d in to_remove:
    print(f"Removing {d}")
    d.unlink()

src = matches[0]
print(f"Copying {src}")
shutil.copy(src, device)
print("Done.")

