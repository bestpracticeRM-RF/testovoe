---
name: shoplite-stand
description: Run and debug the ShopLite DevOps test stand (stage 2 live-debugging on the VPS). Use whenever the user mentions shoplite, тестовое (DevOps задание ShopLite), стенд, этап 2 / второй этап, "сломали стенд", edge/openresty 8080, checkout, kind-кластер shoplite, 502/500 у магазина, or asks to fix/diagnose something on the stand — even indirectly ("магазин лёг", "ничего не открывается на 8080").
---

# ShopLite stand: operation and live-debug playbook

Test assignment stand (DevOps, two-stage). Stage 1 is DONE and submitted (8 commits in repo, REPORT.md). Stage 2 = they send ONE command that breaks the stand; you find the cause and fix it **while narrating hypotheses → command → output → conclusion in the chat**. This skill is the map of the stand + the diagnostic playbook.

## Access chain (Windows → WSL → VPS)

```
wsl -d Ubuntu-26.04 -- bash -lc "ssh root@201.51.6.26 '<command>'"
```

- VPS: `root@201.51.6.26`, auth by WSL key `~/.ssh/id_ed25519` (already installed).
- Work dir on VPS: `~/shoplite-work` (repo/ with full git history, casts/, REPORT.md, TASK.md).
- NEVER nest quotes through cmd → wsl → ssh. Write a script to `C:\Users\btk\Documents\ai\тестовое\batch.sh`, then:
  `wsl -d Ubuntu-26.04 -- bash -lc "scp -q /mnt/c/Users/btk/Documents/ai/тестовое/batch.sh root@201.51.6.26: && ssh root@201.51.6.26 'bash ~/batch.sh'"`
- Record every work session: `ssh … 'bash ~/vps-runner.sh <NN-name>'` runs `~/batch.sh` under asciinema into `casts/`. Set `export TERM=xterm PAGER=cat GIT_PAGER=cat` in every batch (otherwise `git diff` hangs the recording on `less`).
- Mirror of everything: github.com/bestpracticeRM-RF/testovoe (push from WSL `~/shoplite-work`).

## Topology (memorize the ports)

```
client → 127.0.0.1:8080 → docker shop-edge (openresty, container port 80, --network kind)
  → upstream shoplite-control-plane:31994 (NodePort, resolved inside docker net "kind")
  → svc/shop (port 80 → targetPort 8800) → pods app=shop (image shop:v3, 2 replicas, :8800)
  → svc/mariadb:3306 → pod mariadb (mariadb:11.4, --max-connections=28, emptyDir data!)
```

Key facts:

- **ConfigMap `shop-config`** → mounted as DIRECTORY `/etc/shop` (no subPath); app hot-reloads by mtime → flag changes arrive in ~30–90 s WITHOUT pod restart. Log line to confirm: `config reloaded: checkout_enabled=…`. `checkout_enabled=true` is the required final state (POST /checkout → 201).
- **Pool**: bounded by semaphore, pool_size=4 per pod; invalid coupon returns conn to pool (leak was FIXED in A5). Metrics endpoint `/metrics`: `shop_pool_in_use / shop_pool_idle`.
- **mariadb data is emptyDir**: deleting the mariadb pod loses orders but schema+products are auto-recreated from ConfigMap `mariadb-init` on start. max_connections=28 → leaks/scale-outs hit it FAST (that's by design of the task).
- **Edge config**: ansible `ansible/edge.yml` deploys vhost to `/usr/local/openresty/nginx/conf/sites-enabled/shop.conf` (NOT conf.d — that was bug A2) and renders upstream from `ansible/group_vars/edge.yml` (upstream_port 31994). Repeat run must be `changed=0` (criterion). Runs via docker connection plugin against container `shop-edge`.
- **up.sh is re-runnable** (~5 min from scratch: builds image, kind load, applies k8s/, edge container, ansible). Last resort to rebuild everything: `./down.sh && ./up.sh` (commit history survives; stand state resets).

## Already fixed in stage 1 — do NOT "refix"

| Fix | Commit | Note |
|---|---|---|
| svc targetPort 8000→8800 | a669a4a | if 502 again — someone re-broke it |
| vhost → sites-enabled + idempotent allowlist | 5ce6516 | conf.d is a dead dir |
| no-subPath mount + hot-reload | a60800a | file in pod DOES update in kube 1.32 |
| pool leak + semaphore bound (image shop:v3) | abfd1c4 | v2 leaks on invalid coupon |
| checkout_enabled=true | c980404 | required final state |

## Diagnostic playbook by symptom

Start EVERY case in the chat with a hypothesis sentence, then run, then paste the output snippet, then conclude. Fix through repo + `kubectl apply` (commit per fix), never by `kubectl edit` on live objects (task rule; recordings must show it).

### 502 from edge (127.0.0.1:8080)
Break in chain edge→node→svc→pod. In order:
1. `docker logs shop-edge --tail 20` → look at `ua="upstream:port"`: shows where edge actually sent traffic.
2. `docker exec shoplite-control-plane curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:31994/products` → node level OK?
   - Node OK + edge 502 → edge config (someone edited shop.conf/metrics-allow inside the container, or nginx not reloaded): `docker exec shop-edge openresty -T 2>/dev/null | grep -E 'server shoplite|include'` vs repo. Fix: repair repo file if changed, then `cd ansible && ansible-playbook edge.yml` (idempotent, will `changed` back to correct).
   - Node fails → kubectl level: `kubectl -n shop get endpoints shop` (empty? selector broken or no ready pods), `kubectl -n shop get svc shop -o custom-columns=t:.spec.ports[0].targetPort,n:.spec.ports[0].nodePort` (targetPort must be 8800, nodePort 31994 — edge group_vars hardcode 31994; if NodePort changed, fix BOTH svc and group_vars in repo).
3. `kubectl -n shop get pods -o wide` — ready? `kubectl -n shop describe pod -l app=shop | tail -20` for events.
4. Endpoints empty + pods Running/Ready → selector/labels mismatch (someone patched deployment labels): compare `kubectl get deploy shop -o jsonpath='{.spec.selector}'` vs pod labels.

### 500 from app (`Too many connections` / pool)
1. `kubectl -n shop logs deploy/shop --tail=30` — look for `(1040, 'Too many connections')`, `PoolExhausted`, `config reloaded`.
2. `curl -s http://127.0.0.1:8080/metrics | grep shop_pool` — in_use pinned at 4 & idle 0 = connection leak or DB saturation.
3. Check image wasn't rolled back to v2: `kubectl -n shop get deploy shop -o jsonpath='{.spec.template.spec.containers[0].image}'` — must be `shop:v3`. If v2: fix repo k8s/30-app.yaml + apply (v2 leaks on invalid coupons → the whole incident 17.09 again).
4. mariadb side: `kubectl -n shop exec deploy/mariadb -- sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -e "SHOW VARIABLES LIKE \"max_connections\"; SHOW PROCESSLIST;"'` — who holds connections; count by user/host. If max_connections was lowered → fix `k8s/10-mariadb.yaml` args `--max-connections=28` (28 is the designed value) + apply + delete pod (Recreate strategy).
5. Rollout stuck with old pods terminating forever (classic after a leak): leaked conns live in OLD pods; new pod can't pass readiness (1040). Fix: `kubectl -n shop delete pod <old-pod-names>` — closing their conns lets the new pod go Ready. (This exact deadlock happened in stage 1, cast 08→09.)

### checkout suddenly 503 "checkout disabled"
1. `kubectl -n shop get cm shop-config -o jsonpath='{.data.shop\.ini}' | grep checkout_enabled` → if false: someone flipped CM. Fix in repo `k8s/20-app-config.yaml` → true → `kubectl apply` → wait up to ~90 s (kubelet sync + mtime reload), confirm `config reloaded` in logs, then 201.
2. CM says true but 503 → app didn't reload: check mount is still a dir (not subPath) in deployment, and `kubectl exec deploy/shop -- grep checkout /etc/shop/shop.ini`. If file stale >2 min → kubelet issue, `kubectl -n shop rollout restart deploy/shop` as a last resort (acceptable; note it).

### 8080 refuses connection entirely
`docker ps | grep shop-edge` — container gone/stopped: `docker start shop-edge` (or re-run the `docker run` block from up.sh: `docker run -d --name shop-edge --network kind -p 127.0.0.1:8080:80 shop-edge:1`).

### Pods CrashLoop / not Ready
1. `kubectl -n shop logs deploy/shop --previous --tail=30` (python traceback = code/config broke; someone edited shop.py in repo and rebuilt? Check `git -C ~/shoplite-work/repo status`).
2. Readiness is `/ready` = DB SELECT 1 → if DB unreachable: `kubectl -n shop get pods` (mariadb up?), svc/mariadb exists? CoreDNS: `kubectl -n kube-system get deploy coredns` (scaled to 0 → name resolution fails → pymysql host error).
3. Env: DB_PASSWORD comes from Secret `db` — if secret deleted/re-created with new key, pods must restart to pick it up.

### Something edited the live cluster that git doesn't know
`kubectl -n shop get deploy,svc,cm,secret -o yaml | grep -A5 creationTimestamp` diff mentally vs repo; the source of truth is `~/shoplite-work/repo/k8s/` + `ansible/`. Re-apply from repo restores the designed state; commit anything you change.

## Environment pitfalls (already burned by these)

- kind: ONLY stable releases (v0.33.0). The "latest" redirect once gave an alpha that hangs forever on "Ensuring node image".
- `docker build` needs buildx installed (Dockerfile uses `COPY --chmod`).
- WSL networking is in mirrored mode (`C:\Users\btk\.wslconfig`) because AmneziaVPN on the host blocks WSL NAT — do NOT remove that file.
- WSL VM sleeps when no sessions → for long local runs keep a session open; the stand itself lives on the VPS (unaffected).
- asciinema needs `--overwrite` to re-record a cast name; recordings must keep `PAGER=cat`.
- Timezone on VPS is UTC (incident materials: Slack = Europe/Moscow = UTC+3).

## Stage-2 session protocol (do exactly this)

1. Open the batch/runner recording BEFORE touching anything (they watch the process, тупики are fine and even good).
2. For each step write in chat: **Гипотеза → Команда → Вывод (фрагмент) → Заключение**. Never claim output you didn't run.
3. Fix = edit repo file → commit (`git -C ~/shoplite-work/repo commit`) → `kubectl apply` (or `ansible-playbook edge.yml` for edge). Commit message format from stage 1: `A<N>: what and why`.
4. After each fix verify the trio: `products → 200`, `POST /checkout → 201`, `/metrics` pool sane. End with `kubectl -n shop get pods` all 1/1.
5. Do NOT run `down.sh`; up.sh re-run is the sanctioned rebuild path if everything is on fire.

## One-command health snapshot (start here on any breakage)

```bash
curl -s -o /dev/null -w 'products -> %{http_code}\n' http://127.0.0.1:8080/products
curl -s -o /dev/null -w 'checkout -> %{http_code}\n' -X POST -H 'Content-Type: application/json' -d '{"sku":"SKU-9538","qty":1}' http://127.0.0.1:8080/checkout
kubectl -n shop get pods,svc,endpoints
curl -s http://127.0.0.1:8080/metrics | grep shop_pool
docker ps --format '{{.Names}} {{.Status}}'
kubectl -n shop logs deploy/shop --tail=15
```
