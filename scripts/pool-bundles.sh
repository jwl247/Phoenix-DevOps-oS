#!/usr/bin/env bash
# pool-bundles.sh — the repo section of the clone pool (Jerry 2026-10-07: "make a repo section
# for the sectors and the complete phoenix").
#
#   phoenix-sector1.tar .. phoenix-sector4.tar   one per sector
#   phoenix-system.tar                           the complete Phoenix (every tracked file plus
#                                                untracked-not-ignored work, archive/ included)
#
# Same names every run, so each run is the next VERSION of the same pool row; a tar whose
# files did not change is byte-identical (sorted, fixed owner) and intake keeps the existing
# version. Restore: `intake clone phoenix-sector2.tar` (or `genie clone ...`), then `tar -xf`.
#
# Usage (Git Bash, from anywhere):  scripts/pool-bundles.sh [sector1 sector2 ... | system]
#   no arguments = all four sectors + the complete Phoenix.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${PHOENIX_BUNDLES:-/f/Phoenix/bundles}"
mkdir -p "${OUT}"
cd "${REPO}"

targets=("$@")
[[ ${#targets[@]} -eq 0 ]] && targets=(sector1 sector2 sector3 sector4 system)

list=$(mktemp); trap 'rm -f "${list}"' EXIT
made=()
for t in "${targets[@]}"; do
  case "${t}" in
    sector[1-4]) git ls-files -co --exclude-standard -- "${t}" > "${list}"; name="phoenix-${t}.tar" ;;
    system)      git ls-files -co --exclude-standard            > "${list}"; name="phoenix-system.tar" ;;
    *) echo "[pool-bundles] unknown section '${t}' (sector1-4 or system)" >&2; exit 2 ;;
  esac
  n=$(wc -l < "${list}")
  [[ "${n}" -eq 0 ]] && { echo "[pool-bundles] ${t}: no files, skipped"; continue; }
  # Sorted + fixed owner: the same files always make the same bytes (no new version for nothing).
  tar --sort=name --owner=0 --group=0 --numeric-owner -cf "${OUT}/${name}.tmp" -T "${list}"
  mv -f "${OUT}/${name}.tmp" "${OUT}/${name}"
  echo "[pool-bundles] ${name}: ${n} files, $(( $(wc -c < "${OUT}/${name}") / 1024 )) KB"
  made+=("${OUT}/${name}")
done

[[ ${#made[@]} -gt 0 ]] && bash "${REPO}/scripts/hsf-intake.sh" "${made[@]}"
