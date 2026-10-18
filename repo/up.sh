#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

CLUSTER=shoplite
EDGE_PORT=${EDGE_PORT:-8080}

for bin in docker kind kubectl ansible-playbook; do
  command -v "$bin" >/dev/null || { echo "missing: $bin" >&2; exit 1; }
done

kind get clusters 2>/dev/null | grep -qx "$CLUSTER" || kind create cluster --config .stand/kind.yaml
kubectl config use-context "kind-$CLUSTER" >/dev/null

IMAGE=$(awk '$1 == "image:" && $2 ~ /^shop:/ {print $2; exit}' k8s/30-app.yaml)
docker build -q -t "$IMAGE" app
kind load docker-image "$IMAGE" --name "$CLUSTER"

if ! kubectl get ns shop >/dev/null 2>&1; then
  # Reproduce production history once: release v2 went out with the release config,
  # the on-call hotfix to shop-config was applied later.
  kubectl apply -f k8s/00-namespace.yaml
  # DB credentials: random, generated once, never stored in git (A8).
  # Must exist BEFORE mariadb: pods resolve secretKeyRef at start.
  if ! kubectl -n shop get secret db >/dev/null 2>&1; then
    kubectl -n shop create secret generic db \
      --from-literal=root-password="$(openssl rand -hex 12)" \
      --from-literal=password="$(openssl rand -hex 12)"
  fi
  kubectl apply -f k8s/10-mariadb.yaml
  kubectl -n shop rollout status deploy/mariadb --timeout=300s
  kubectl apply -f .stand/app-config.release.yaml -f k8s/30-app.yaml
  kubectl -n shop wait pod -l app=shop --for=condition=Ready --timeout=300s
fi
# DB credentials: generated at first bring-up, never stored in git (A8)
if ! kubectl -n shop get secret db >/dev/null 2>&1; then
  kubectl -n shop create secret generic db \
    --from-literal=root-password="$(openssl rand -hex 12)" \
    --from-literal=password="$(openssl rand -hex 12)"
fi

kubectl apply -f k8s/

# observability layer (A16); optional — do not fail the bring-up on it
kubectl apply -f monitoring/k8s/ || echo "monitoring apply failed, continuing"

docker build -q -t shop-edge:1 -f .stand/edge.Dockerfile .stand
if ! docker inspect shop-edge >/dev/null 2>&1; then
  docker run -d --name shop-edge --network kind -p "127.0.0.1:${EDGE_PORT}:80" -p "127.0.0.1:8443:443" shop-edge:1
fi
(cd ansible && ansible-playbook edge.yml)

echo "stand is up: http://127.0.0.1:${EDGE_PORT}/products"
