#!/usr/bin/env python3
"""Parse-only manifest lint (CI-safe, no cluster needed)."""
import glob, sys
import yaml
docs = 0
for f in sorted(glob.glob('k8s/*.yaml') + glob.glob('k8s/*.yml') + ['.stand/app-config.release.yaml']):
    for i, d in enumerate(yaml.safe_load_all(open(f))):
        assert isinstance(d, dict) and 'kind' in d, f'{f}[{i}] not a k8s doc'
        docs += 1
print(f'OK: {docs} k8s docs parsed')
