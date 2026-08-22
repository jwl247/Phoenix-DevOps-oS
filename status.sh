#!/usr/bin/env bash
# =============================================================================
# Phoenix DevOps OS — Session Status Check
# =============================================================================

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== PHOENIX STATUS === $(date)"
echo ""
echo "── Sector tree (${REPO_ROOT}) ──"
for s in sector1 sector2 sector3 sector4 phoenix-core scripts tools dashboard; do
  if [[ -d "${REPO_ROOT}/${s}" ]]; then
    count=$(find "${REPO_ROOT}/${s}" -type f 2>/dev/null | wc -l)
    echo "  ${s}: ${count} files"
  else
    echo "  ${s}: NOT FOUND"
  fi
done
echo ""
echo "── breach_coms mounts ──"
for m in g f e d; do
  [[ -d "/mnt/${m}" ]] && echo "  /mnt/${m} : MOUNTED" || echo "  /mnt/${m} : NOT MOUNTED (WSL/Bare metal)"
done
echo ""
echo "── systemd (Linux) ──"
if command -v systemctl &>/dev/null; then
  systemctl --user is-system-running 2>/dev/null || echo "  SYSTEMD: degraded or not running"
else
  echo "  SYSTEMD: Windows host (managed via usys / tray)"
fi
echo ""
echo "── UnitedSys / USys ──"
if [[ -f "${REPO_ROOT}/sector2/unitedsys/core/us.py" ]]; then
  echo "  US: operational in sector2/unitedsys"
else
  echo "  US: not found"
fi
echo ""
echo "── Catalog (SQLite) ──"
if [[ -f "${HOME}/.catalog/catalog.db" ]]; then
  sqlite3 "${HOME}/.catalog/catalog.db" "SELECT COUNT(*) || ' packages' FROM packages;" 2>/dev/null || echo "  Catalog: database present"
else
  echo "  Catalog: uninitialized (runs on first intake)"
fi
echo ""
echo "── Git ──"
git -C "${REPO_ROOT}" remote -v 2>/dev/null || echo "  phoenix-devops: git error"
echo ""
echo "=== END STATUS ==="
