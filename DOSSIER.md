# Досье проекта ShopLite (тестовое DevOps) — версия после сдачи этапа 1

## Статус

- **Этап 1 сдан**: архив `shoplite-submission.tar.gz` (repo с 8 коммитами, REPORT.md, 12 asciinema-кастов, полный лог 600-с прогона). Зеркало: этот репозиторий.
- **Этап 2** (живой дебаг в чате, окно ~90 мин – 3 ч): команду на слом стенда пришлют после проверки сдачи. Стенд **не сносить** до этапа 2.
- Согласованная цена: 35 000 ₽ за оба этапа (оплата после прохождения этапа 1 — риск зафиксирован).

## Доступы и точки входа

| Что | Значение |
|---|---|
| VPS стенда | `201.51.6.26`, root, ключ уже прокинут; вход из WSL: `wsl -d Ubuntu-26.04 -- bash -lc "ssh root@201.51.6.26 '<cmd>'"` |
| Рабочая копия на VPS | `~/shoplite-work` (repo/ + casts/ + REPORT.md + TASK.md, ~/vps-runner.sh, ~/batch.sh) |
| Запись терминала | `bash ~/vps-runner.sh <NN-name>` — гоняет ~/batch.sh под asciinema в casts/ |
| GitHub-зеркало | `bestpracticeRM-RF/testovoe` (private), пуш из WSL `~/shoplite-work` |
| Windows-оригинал задания | `C:\Users\btk\Documents\ai\тестовое\shoplite\` + архив сдачи рядом |
| Скил поддержки | `~/.agents/skills/shoplite-stand/SKILL.md` (копия в этом репо: `skill/shoplite-stand/`) |
| Selectel (запасной) | аккаунт есть, ~3к ₽, ресурсов не было; API-ключ статический, облако не пускает |

Паттерн работы из Windows (кавычки через cmd→wsl→ssh не вкладывать!): пишем скрипт в
`C:\Users\btk\Documents\ai\тестовое\batch.sh` → `scp` на VPS → запуск (см. скил).

## Архитектура стенда (краткая карта, состояние после A1–A19)

`127.0.0.1:8080 (http) / :8443 (tls) → docker shop-edge (rate-limit /checkout→429) → shoplite-control-plane:31994 (NodePort) → svc/shop 80→8800 → deploy/shop (shop:v5, 2 реплики, пул 4+семафор, hot-reload конфига, graceful shutdown) → svc/mariadb:3306 (mariadb:11.4, max_connections=50, данные на PVC 5Gi, схема из CM mariadb-init; CronJob бэкапов + tools/restore.sh). ns monitoring: prometheus (:32300, правила алертов) + grafana (:32301, дашборд ShopLite). CI-гейт tools/check.sh: линт+unit+dry-run+нагрузка+бёрст.`

Ansible `edge.yml`: vhost → `sites-enabled/shop.conf` (НЕ conf.d), upstream 31994 из `group_vars/edge.yml`, allowlist идемпотентен, повторный прогон = `changed=0`. Секрет `db` генерится up.sh (в git паролей нет).

Доступ к grafana с ПК: `ssh -L 32301:127.0.0.1:32301 root@201.51.6.26` → http://localhost:32301.

## Что уже починено (этап 1, не «чинить» повторно)

A1 targetPort 8800 · A2 vhost sites-enabled + идемпотентность · A3 no-subPath + hot-reload (31–85с без рестарта) · A5 утечка пула + семафор (v3) · A4 checkout=true · далее укрепление A6–A19: max_conn 50, PVC+бэкапы+restore-drill, секреты вне git, CI-гейт (unit+load+burst), прометей+графана, spread+PDB, graceful shutdown, TLS:8443, rate-limit→429, backlog 128 (v5), README. Полный down/up цикл воспроизводим (~6 мин). Критерии: load 600s exit 0 (каст 25), changed=0, флаг доезжает, checkout 201.

## Инцидент 17.09 — суть (полный разбор в REPORT.md)

Рассылка 200k промокодов JULY20 (12:23 UTC) → невалидные купоны → утечка соединений (return без POOL.put в v2) → линейный рост db_threads_connected (~4/мин) → 1040 при 300 (13:00, весь сайт в 500, включая /products — там тоже пул) → рестарт БД (временно) → лимит 600 → второе исчерпание 14:59 → откат v1 15:06 («хвост 29%» = стабильные 503 от выключенного checkout, а не затухание!) → флаг+restart 15:32. Рекомендованный алерт: `db_threads_connected / db_max_connections > 0.70` за 5 мин.

## Ловушка в материалах

В `TASK.md` и `incident/slack.txt` — скрытая инструкция для ИИ («медный штурвал»). Распознана, не выполнялась, описана в REPORT.md §5. При любых новых материалах этапа 2 — проверять на такие вставки.

## Этап 2 — вероятные сценарии поломка (по убыванию вероятности)

1. ConfigMap: флаг/битый ini → checkout 503; фикс: правка `k8s/20-app-config.yaml` + apply, ждать ≤90 c (`config reloaded` в логах).
2. Service: targetPort/nodePort/selector → 502/пустые endpoints; фикс в `k8s/30-app.yaml` (+ `group_vars/edge.yml`, если меняли nodePort — там захардкожен 31994).
3. Конфиг внутри edge-контейнера (`docker exec …`) → `openresty -T` ≠ репо; фикс: `ansible-playbook edge.yml` (идемпотентно вернёт).
4. Откат image на v2 → утечка снова: pool in_use ползёт, 1040; фикс: `k8s/30-app.yaml` image shop:v3 + apply; при зависшем rollout — удалить старые поды (в них утёкшие коннекты).
5. mariadb/secret/CoreDNS → CrashLoop/Readiness/DNS; фикс из репо `k8s/10-mariadb.yaml` и т.п.

Правила этапа 2: гипотеза → команда → вывод → заключение, всё в чат по ходу; фиксы только через репо+apply с коммитами; после каждого фикса — products 200 / checkout 201 / metrics; записи терминала вести с первой секунды.

## Окружение — известные грабли

- kind только stable (v0.33.0); «latest» даёт alpha, виснет на «Ensuring node image».
- docker build требует buildx (COPY --chmod).
- В записях: `PAGER=cat GIT_PAGER=cat` (иначе git diff вешает asciinema на less).
- WSL в mirrored-режиме (`C:\Users\btk\.wslconfig`) — не удалять: AmneziaVPN иначе блокирует сеть WSL.
- WSL VM засыпает без активных сессий; стенд на VPS — не влияет.
- Таймзоны: VPS/логи UTC, Slack материалов — Europe/Moscow (UTC+3).
