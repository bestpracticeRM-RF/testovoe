#!/usr/bin/env bash
set -uo pipefail
kind delete cluster --name shoplite
docker rm -f shop-edge
