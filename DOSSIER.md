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

## Архитектура стенда (краткая карта)

`127.0.0.1:8080 → docker shop-edge (openresty, --network kind) → shoplite-control-plane:31994 (NodePort) → svc/shop 80→8800 → deploy/shop (shop:v3, 2 реплики, пул 4+семафор, hot-reload конфига) → svc/mariadb:3306 (mariadb:11.4, --max-connections=28, emptyDir — схема восстанавливается из CM mariadb-init).`

Ansible `edge.yml`: vhost → `sites-enabled/shop.conf` (НЕ conf.d — там был баг A2), allowlist идемпотентен, повторный прогон = `changed=0`.

## Что уже починено в этапе 1 (не « чинить» повторно)

| Фикс | Коммит |
|---|---|
| svc targetPort 8000→8800 | a669a4a |
| vhost в sites-enabled + идемпотентный allowlist | 5ce6516 |
| mount каталогом (без subPath) + hot-reload по mtime (флаг доезжает за 31–85 c без рестарта) | a60800a |
| утечка пула на невалидных купонах + семафор (образ shop:v3) | abfd1c4 |
| checkout_enabled=true (финальное состояние) | c980404 |

Критерии этапа 1: load.py 600s — exit 0, 0 5xx (~9000 запросов, p99 0.05с); ansible changed=0; флаг доезжает без рестарта; checkout 201.

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
