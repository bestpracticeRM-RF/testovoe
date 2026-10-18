#!/bin/bash
# usage: run-rec.sh <cast-name>  — runs ~/batch.sh under asciinema into shoplite-work/casts/<name>.cast
export TERM=xterm PAGER=cat GIT_PAGER=cat
pkill -f 'asciinema rec' 2>/dev/null
sleep 1
cd ~/shoplite-work/repo || exit 1
mkdir -p ../casts
asciinema rec -q --overwrite -c "bash ~/batch.sh" "../casts/$1.cast"
echo "CAST-SAVED: ../casts/$1.cast (exit=$?)"
