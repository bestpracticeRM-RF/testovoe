# ShopLite stand

Тестовый стенд магазина: `edge (openresty, ansible) → k8s NodePort → shop (python) → MariaDB`.

## Quickstart

```
./up.sh                                     # поднять (kind + k8s + edge + monitoring)
curl http://127.0.0.1:8080/products         # витрина
python3 tools/load.py --duration 600        # нагрузка (критерий: 0 5xx)
./down.sh                                   # снести
```

Порты: `8080` edge, `8443` edge TLS, `31994` NodePort, `32300` prometheus, `32301` grafana.

## Карта

| Компонент | Где | Управляется |
|---|---|---|
| edge (openresty + TLS + rate-limit) | docker `shop-edge` | `ansible/edge.yml` |
| shop (image shop:v5, 2 реплики, bounded pool, hot-reload конфига) | ns `shop` | `k8s/30-app.yaml` |
| конфиг приложения | ConfigMap `shop-config` → `/etc/shop` | `k8s/20-app-config.yaml` |
| mariadb (PVC 5Gi, max_connections=50, схема из CM) | ns `shop` | `k8s/10-mariadb.yaml` |
| бэкапы (CronJob mysqldump, 7 дней) + restore | PVC `mariadb-backups` | `tools/restore.sh` |
| мониторинг (prometheus + grafana + alerts) | ns `monitoring` | `monitoring/k8s/` |
| CI-гейт (lint, dry-run, unit, нагрузка) | — | `tools/check.sh`, `.github/workflows/ci.yml` |

Секрет `db` генерируется при первом подъёме (в git паролей нет).

## Типовые поломки (плейбук)

| Симптом | Смотреть | Фикс |
|---|---|---|
| 502 | `docker logs shop-edge` → `kubectl get endpoints` → `get svc targetPort/nodePort` | apply из репо |
| 500 `Too many connections` | `SHOW PROCESSLIST`, `/metrics` pool, image == v5? | KILL сессий / apply |
| checkout 503 | CM `shop-config` + `config reloaded` в логах | apply `20-app-config.yaml`, ~60-90с |
| 429 на /checkout | rate-limit (10r/s, burst 20) | это норма при бёрсте |
| данные пропали после падения пода | нет: данные на PVC | `tools/restore.sh` если нужно откатиться |

Правило: живое ≠ репо → сначала сверка, фикс всегда коммитом + apply.
