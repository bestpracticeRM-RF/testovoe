#!/bin/bash
# Restore the shop DB from the newest dump on the mariadb-backups PVC.
# Usage: tools/restore.sh [dump-file-name]   (default: newest shop-*.sql.gz)
set -euo pipefail
NS=shop

NEWEST="${1:-}"
if [ -z "$NEWEST" ]; then
  NEWEST=$(kubectl -n "$NS" run ls-backups --rm -i --restart=Never --image=mariadb:11.4 \
    --overrides='{"spec":{"containers":[{"name":"ls","image":"mariadb:11.4","command":["sh","-c","ls -1t /backups/shop-*.sql.gz | head -1"],"volumeMounts":[{"name":"backups","mountPath":"/backups"}]}],"volumes":[{"name":"backups","persistentVolumeClaim":{"claimName":"mariadb-backups"}}]}}' \
    2>/dev/null | grep -o 'shop-[0-9-]*\.sql\.gz' | head -1)
fi
echo "restoring from: $NEWEST"
[ -n "$NEWEST" ] || { echo 'no backups found'; exit 1; }

kubectl -n "$NS" delete job restore-drill --ignore-not-found >/dev/null
cat > /tmp/restore-job.yaml <<'YAML'
apiVersion: batch/v1
kind: Job
metadata: {name: restore-drill, namespace: shop}
spec:
  backoffLimit: 2
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: restore
          image: mariadb:11.4
          command: ["sh", "-c"]
          args: ["gunzip -c /backups/__DUMP__ | mariadb -hmariadb -ushop -p\"$DB_PASSWORD\" shop"]
          env:
            - name: DB_PASSWORD
              valueFrom: {secretKeyRef: {name: db, key: password}}
          volumeMounts:
            - {name: backups, mountPath: /backups}
      volumes:
        - name: backups
          persistentVolumeClaim: {claimName: mariadb-backups}
YAML
sed -i "s|__DUMP__|$NEWEST|" /tmp/restore-job.yaml
kubectl apply -f /tmp/restore-job.yaml >/dev/null
kubectl -n "$NS" wait --for=condition=complete job/restore-drill --timeout=180s
echo "restore job completed"
kubectl -n "$NS" delete job restore-drill >/dev/null
