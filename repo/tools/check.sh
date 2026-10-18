#!/bin/bash
# CI gate: parse manifests, dry-run apply, regression load (leak class A5)
set -e
cd "$(dirname "$0")/.."
echo "--- yaml parse all manifests:"
python3 - <<'PY'
import yaml, glob, sys
files = sorted(glob.glob('k8s/*.yaml') + glob.glob('k8s/*.yml') + ['.stand/app-config.release.yaml'])
docs = 0
for f in files:
    for i, d in enumerate(yaml.safe_load_all(open(f))):
        assert isinstance(d, dict) and 'kind' in d, f'{f}[{i}] not a k8s doc'
        docs += 1
print(f'OK: {len(files)} files, {docs} docs parsed')
PY
echo "--- kubectl client dry-run:"
kubectl apply --dry-run=client -f k8s/ >/dev/null && echo "OK: apply dry-run clean"
echo "--- regression: 2 min load with invalid coupons must be 0 5xx:"
python3 tools/load.py --duration 120
echo "GATE-PASSED"
