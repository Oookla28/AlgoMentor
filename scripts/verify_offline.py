"""Run the cold-start harness without changing the host network or real data."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

if __name__ == '__main__':
    process = subprocess.run([sys.executable, str(ROOT / 'scripts/offline_probe.py')],
                             cwd=ROOT, capture_output=True, text=True, timeout=180)
    rows = [line.removeprefix('ALGOMENTOR_OFFLINE_RESULT=') for line in process.stdout.splitlines()
            if line.startswith('ALGOMENTOR_OFFLINE_RESULT=')]
    result = json.loads(rows[-1]) if rows else {'status': 'FAILED', 'error_type': 'ProbeTerminated', 'return_code': process.returncode}
    path = ROOT / 'tests/evaluation/offline_cold_start.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'output': 'tests/evaluation/offline_cold_start.json', 'status': result['status'],
                      'error_type': result.get('error_type'), 'message': result.get('message')}, ensure_ascii=False))
    raise SystemExit(0 if result['status'] == 'PASSED' else 1)
