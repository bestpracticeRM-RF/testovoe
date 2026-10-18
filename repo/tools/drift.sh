#!/bin/bash
# Drift detector: live cluster vs repo. "repo is the source of truth" as one command.
# Exit 0 = no drift; exit 1 = drift found (or error).
set -uo pipefail
cd "$(dirname "$0")/.."
RC=0

echo '--- kubectl diff k8s/:'
kubectl diff -f k8s/; case $? in
  0) echo 'k8s: no drift' ;;
  1) echo 'k8s: DRIFT DETECTED' ; RC=1 ;;
  *) echo 'k8s: diff error'    ; RC=1 ;;
esac
echo '--- kubectl diff monitoring/k8s/:'
kubectl diff -f monitoring/k8s/ >/dev/null 2>&1; case $? in
  0) echo 'monitoring: no drift' ;;
  1) echo 'monitoring: DRIFT DETECTED' ; RC=1 ;;
  *) echo 'monitoring: diff error'    ; RC=1 ;;
esac
echo '--- ansible edge (--check --diff):'
OUT=$(cd ansible && ansible-playbook edge.yml --check --diff 2>&1 | grep -E 'PLAY RECAP' -A1)
echo "$OUT"
echo "$OUT" | grep -q 'changed=0' || RC=1
exit $RC
