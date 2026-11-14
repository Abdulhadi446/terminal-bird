#!/usr/bin/env bash
# install.sh - install terminal-bird and make it runnable from any shell
# Usage: ./install.sh [--user|--system|--prefix DIR]

set -euo pipefail

REPO_URL="${REPO_URL:-https://raw.githubusercontent.com/Abdulhadi446/terminal-bird/main}"

USER_LEVEL=1
PREFIX=""

while (( $# > 0 )); do
  case "$1" in
    --system|-s) USER_LEVEL=0;;
    --user|-u) USER_LEVEL=1;;
    --prefix) shift; PREFIX="${1:?--prefix needs a directory}";;
    --help|-h)
      cat <<'HELP'
Usage: ./install.sh [--user|--system|--prefix DIR]

  --user     install under ~/.local (default)
  --system   install under /usr/local (needs root or sudo)
  --prefix   custom install prefix

After installing, run:  bird        (or the full name: terminal-bird)
HELP
      exit 0
      ;;
    *) echo "unknown argument: $1" >&2; exit 2;;
  esac
  shift
done

log() { printf 'install: %s\n' "$*"; }
fail() { printf 'install: error: %s\n' "$*" >&2; exit 1; }

PYTHON_BIN="$(command -v python3 || command -v python || true)"
[[ -z "$PYTHON_BIN" ]] && fail "python 3 is not installed."
if ! "$PYTHON_BIN" -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)'; then
  fail "python 3.9 or newer is required."
fi

SCRIPT_DIR=""
if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
  SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)" || true
fi
SOURCE_PY=""
for candidate in "$SCRIPT_DIR/flappy.py" "$PWD/flappy.py"; do
  if [[ -f "$candidate" ]]; then SOURCE_PY="$candidate"; break; fi
done
if [[ -z "$SOURCE_PY" ]]; then
  log "flappy.py not found next to the installer; downloading it..."
  TMP_PY="$(mktemp)"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$REPO_URL/flappy.py" -o "$TMP_PY"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$TMP_PY" "$REPO_URL/flappy.py"
  else
    fail "no flappy.py and no curl/wget to download one"
  fi
  SOURCE_PY="$TMP_PY"
fi

if [[ -n "$PREFIX" ]]; then
  BASE_DIR="$PREFIX"
  BIN_DIR="$PREFIX/bin"
else
  if (( USER_LEVEL == 0 )); then
    BASE_DIR="/usr/local"
    BIN_DIR="/usr/local/bin"
  else
    BASE_DIR="$HOME/.local"
    BIN_DIR="$HOME/.local/bin"
  fi
fi

mkdir -p "$BIN_DIR"
if [[ ! -w "$BIN_DIR" ]]; then
  fail "cannot write to $BIN_DIR (try sudo ./install.sh --system or --user)"
fi

APP_DIR="$BASE_DIR/share/terminal-bird"
mkdir -p "$APP_DIR"

log "installing python entry: $SOURCE_PY -> $BIN_DIR/terminal-bird"
install -m 0644 "$SOURCE_PY" "$APP_DIR/flappy.py"
printf '#!/bin/sh\nexec "%s" "%s" "$@"\n' "$PYTHON_BIN" "$APP_DIR/flappy.py" > "$BIN_DIR/terminal-bird"
chmod 0755 "$BIN_DIR/terminal-bird"
# install a short alias
ln -sf "$BIN_DIR/terminal-bird" "$BIN_DIR/bird"

# optional desktop entry (Linux/BSD)
if [[ -d "$HOME/.local" ]]; then
  DESK_DIR="$HOME/.local/share/applications"
  mkdir -p "$DESK_DIR"
  cat > "$DESK_DIR/terminal-bird.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Terminal Bird
Comment=A flappy arcade bird, drawn entirely in your terminal
Exec=$BIN_DIR/terminal-bird
Terminal=true
Categories=Game;
DESKTOP
  command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DESK_DIR" >/dev/null 2>&1 || true
fi

# PATH help for user installs
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
      if [[ -f "$rc" ]]; then
        if ! grep -qF "$BIN_DIR" "$rc"; then
          printf '\n# terminal-bird\nexport PATH="%s:$PATH"\n' "$BIN_DIR" >> "$rc"
          log "added $BIN_DIR to $rc (restart your shell)"
        fi
      fi
    done
    ;;
esac

if [[ ! -x "$BIN_DIR/terminal-bird" || ! -e "$BIN_DIR/bird" ]]; then
  fail "install step did not place the terminal-bird executable"
fi

cat <<EOF

Terminal Bird is installed.

Run it from any directory with:
    bird
(terminal-bird works too.)

If your shell doesn't find it yet, either restart your shell or run:
    export PATH="$BIN_DIR:\$PATH"

EOF

if [[ -n "${TMP_PY:-}" && -f "${TMP_PY:-}" ]]; then rm -f "$TMP_PY"; fi