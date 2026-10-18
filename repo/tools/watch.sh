#!/bin/bash
# Polls app /metrics and DB Threads_connected; prints ALERT when thresholds crossed.
# Stand-grade watchdog; in prod these are prometheus rules (monitoring/prometheus-alerts.yaml)
URL=${1:-http://127.0.0.1:8080}
while sleep 15; do
  read in_use idle < <(curl -s -m 3 $URL/metrics | awk '/shop_pool_in_use/{i=$2}/shop_pool_idle/{d=$2}END{print i, d}')
  threads=$(kubectl -n shop exec deploy/mariadb -- sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e "SHOW STATUS LIKE \"Threads_connected\"" 2>/dev/null' | awk '{print $2}')
  maxc=$(kubectl -n shop exec deploy/mariadb -- sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e "SHOW VARIABLES LIKE \"max_connections\"" 2>/dev/null' | awk '{print $2}')
  ratio=$(python3 -c "print(f'{$threads/$maxc:.2f}')" 2>/dev/null)
  ts=$(date -u +%H:%M:%S)
  if python3 -c "exit(0 if $ratio > 0.70 else 1)" 2>/dev/null; then
    echo "$ts ALERT db_connections ratio=$ratio threads=$threads/$maxc pool in_use=$in_use idle=$idle"
  else
    echo "$ts ok    db_connections ratio=$ratio threads=$threads/$maxc pool in_use=$in_use idle=$idle"
  fi
done
