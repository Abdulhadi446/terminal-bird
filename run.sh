#!/usr/bin/env bash
# Shortcut: run the game straight from the repository.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 flappy.py "$@"