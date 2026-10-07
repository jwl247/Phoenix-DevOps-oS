#!/usr/bin/env bash
# phoenix-paths.sh — slash-insensitive paths for every Phoenix command (bash side: Git Bash + Linux).
# Phoenix DevOps OS | jwl247 | GPL v3
# Jerry 2026-10-07: "make all our system slash insensitive, seeing how we are Windows and Linux".
# Same rule as scripts/phoenix-paths.ps1 and scripts/phoenix_paths.py (tested together).
#   source bin/phoenix-paths.sh
#   phx_path 'F:\Phoenix\x'      -> /f/Phoenix/x on Git Bash, /mnt/f/Phoenix/x on Linux if /mnt/f exists
#   phx_args "$@"; set -- "${PHX_ARGS[@]}"      fix every path-looking argument, leave the rest
# Only arguments that LOOK like a path change: URLs, flags (-x, --x) and words pass through.

phx_is_msys() { [[ "$(uname -s 2>/dev/null)" == MINGW* || "$(uname -s 2>/dev/null)" == MSYS* || "$(uname -s 2>/dev/null)" == CYGWIN* ]]; }

phx_path_like() {
  local a="$1"
  [[ -z "$a" || "$a" == -* ]] && return 1
  [[ "$a" =~ ^[a-zA-Z][a-zA-Z0-9+.-]+:// ]] && return 1
  [[ "$a" =~ ^[a-zA-Z]:([\\/]|$) || "$a" =~ ^/mnt/[a-zA-Z](/|$) || "$a" =~ ^/[a-zA-Z]/ || "$a" =~ ^~[\\/] || "$a" =~ ^\.{1,2}[\\/] || "$a" == *\\* ]]
}

phx_path() {
  local t="$1" d rest
  t="${t#\`}"; t="${t%\`}"; t="${t#\"}"; t="${t%\"}"; t="${t#\'}"; t="${t%\'}"
  [[ "$t" =~ ^[a-zA-Z][a-zA-Z0-9+.-]+:// ]] && { printf '%s' "$t"; return; }
  t="${t//\\//}"                                                  # backslashes -> /
  [[ "$t" == "~/"* || "$t" == "~" ]] && t="$HOME${t:1}"
  if [[ "$t" =~ ^([a-zA-Z]):(/.*)?$ ]]; then d="${BASH_REMATCH[1],,}"; rest="${BASH_REMATCH[2]}"
  elif [[ "$t" =~ ^/mnt/([a-zA-Z])(/.*)?$ ]]; then d="${BASH_REMATCH[1],,}"; rest="${BASH_REMATCH[2]}"
  elif phx_is_msys && [[ "$t" =~ ^/([a-zA-Z])(/.*)$ ]]; then d="${BASH_REMATCH[1],,}"; rest="${BASH_REMATCH[2]}"
  else printf '%s' "$t"; return; fi
  if phx_is_msys; then printf '/%s%s' "$d" "$rest"                # Git Bash drive form
  elif [[ -d "/mnt/$d" ]]; then printf '/mnt/%s%s' "$d" "$rest"   # Linux with the drive mounted
  else printf '%s' "$t"; fi                                       # nothing to map to: leave it
}

phx_args() {
  PHX_ARGS=()
  local a
  for a in "$@"; do
    if phx_path_like "$a"; then PHX_ARGS+=("$(phx_path "$a")"); else PHX_ARGS+=("$a"); fi
  done
}
