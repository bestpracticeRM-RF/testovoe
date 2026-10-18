#!/bin/bash
# Nightly stand self-check: drift + full gate, log to casts/, keep 14 days.
export TERM=xterm PAGER=cat GIT_PAGER=cat
DIR=~/shoplite-work/casts
LOG="$DIR/nightly-$(date +%F).log"
{
  echo "=== nightly $(date -u +%FT%TZ) git=$(git -C ~/shoplite-work/repo rev-parse --short HEAD)"
  bash ~/shoplite-work/repo/tools/drift.sh
  echo "drift exit=$?"
  bash ~/shoplite-work/repo/tools/check.sh
  echo "gate exit=$?"
  echo "=== done $(date -u +%FT%TZ)"
} >> "$LOG" 2>&1
find "$DIR" -name 'nightly-*.log' -mtime +14 -delete
