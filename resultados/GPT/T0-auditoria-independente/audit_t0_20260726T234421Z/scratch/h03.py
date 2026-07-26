import os, json, shutil, tempfile, subprocess

run_dir = 'review/T0/runs/run_t0_golden'
paths_found = []

for fn in ['events.jsonl', 'verify_result.json', 'commands.log', 'report.md']:
    fp = os.path.join(run_dir, fn)
    if os.path.exists(fp):
        content = open(fp, 'r', encoding='utf-8', errors='ignore').read()
        for line in content.splitlines():
            if '/home/' in line or '/tmp/' in line:
                paths_found.append((fn, line[:120]))

print(f'Absolute path references found: {len(paths_found)}')
for fn, line in paths_found[:10]:
    print(f'  [{fn}] {line}')

with tempfile.TemporaryDirectory() as tmpdir:
    dst_run = os.path.join(tmpdir, 'run_t0_golden')
    shutil.copytree(run_dir, dst_run)
    PYTEST_PYTHON = '/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/.venv/bin/python'
    res = subprocess.run([PYTEST_PYTHON, '-m', 'cortes.verify', dst_run], cwd='/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper', capture_output=True, text=True)
    print(f'Relocated verify exit code: {res.returncode}')
    print('Verify output snippet:')
    print(res.stdout[:500])
