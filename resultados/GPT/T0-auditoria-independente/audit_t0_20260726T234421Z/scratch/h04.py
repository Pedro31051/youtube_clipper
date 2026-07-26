import os, hashlib, shutil, tempfile, subprocess

run_dir = 'review/T0/runs/run_t0_golden'

def get_hashes(d):
    hashes = {}
    for root, dirs, files in os.walk(d):
        for f in sorted(files):
            fp = os.path.join(root, f)
            with open(fp, 'rb') as fh:
                hashes[fp] = hashlib.sha256(fh.read()).hexdigest()
    return hashes

before = get_hashes(run_dir)

PYTEST_PYTHON = '/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/.venv/bin/python'
res = subprocess.run([PYTEST_PYTHON, '-m', 'cortes.verify', run_dir], cwd='/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper', capture_output=True, text=True)

after = get_hashes(run_dir)

modified = []
created = []
deleted = []

for k in before:
    if k not in after:
        deleted.append(k)
    elif before[k] != after[k]:
        modified.append(k)

for k in after:
    if k not in before:
        created.append(k)

print(f'H04 Readonly Check Results:')
print(f'  Modified: {len(modified)}')
print(f'  Created: {len(created)}')
print(f'  Deleted: {len(deleted)}')
for f in modified:
    print(f'    Mod: {f}')
for f in created:
    print(f'    New: {f}')
