#!/usr/bin/env zsh
# Phoenix DevOps — Session Status Check
# Run this at the start of every Claude Code session
echo "=== PHOENIX STATUS === $(date)"
echo ""
echo "── Sector tree ──"
for s in sector1 sector2 sector3 sector4; do
  count=$(find ~/projects/phoenix-devops/$s -type f 2>/dev/null | wc -l)
  echo "  $s: $count files"
done
echo ""
echo "── breach_coms mounts ──"
for m in g f e d; do
  [[ -d /mnt/$m ]] && echo "  /mnt/$m : MOUNTED" || echo "  /mnt/$m : NOT MOUNTED"
done
echo ""
echo "── systemd ──"
systemctl --user is-system-running 2>/dev/null || echo "  SYSTEMD: degraded or not running"
echo ""
echo "── UnitedSys ──"
cd ~/projects/unitedsys && python3 -m core.us list 2>/dev/null | head -5 || echo "  US: not functional"
echo ""
echo "── Catalog ──"
sqlite3 ~/.catalog/catalog.db "SELECT COUNT(*) || ' packages' FROM packages;" 2>/dev/null
sqlite3 ~/.catalog/glossary.db "SELECT COUNT(*) || ' glossary entries' FROM glossary;" 2>/dev/null
echo ""
echo "── Git ──"
git -C ~/projects/phoenix-devops remote -v 2>/dev/null || echo "  phoenix-devops: no remote (create jwl247/phoenix-devops)"
git -C ~/projects/unitedsys remote -v 2>/dev/null
echo ""
echo "=== END STATUS ==="
