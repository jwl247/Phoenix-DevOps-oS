#!/usr/bin/env bash
# phoenix-peer-agent — what a mesh BUDDY may ask of this box. Nothing else.
# Phoenix DevOps OS | jwl247 | GPL v3
#
# Reached only through SSH as user phoenix-peer, whose key line is
#   restrict,from="10.42.0.0/16,192.168.1.0/24",command="sudo -n /usr/local/sbin/phoenix-peer-agent"
# so the caller never gets a shell: the command it asked for arrives in $SSH_ORIGINAL_COMMAND and must
# be one of these verbs:
#   status                 JSON health report (read-only)
#   heal                   run this box's own heal scripts now, then report
#   export mesh            tar of the mesh known-good (config.yml + .sig + VERSION) for the buddy's version store
#   restore mesh <cfghash> tar on stdin; installed ONLY if the config hashes to <cfghash> AND carries a valid
#                          signature from the Phoenix config key (/etc/nebula/allowed_signers). A buddy can
#                          hand back a version; it cannot invent one.
# Every call goes to the journal: journalctl -t phoenix-peer-agent. Installed by sector3/mesh/phoenix_buddy.py.
set -uo pipefail
VERSION="peer-agent-1.0.0"
C=/etc/nebula; KG=$C/known-good
log() { logger -t phoenix-peer-agent "$*"; }
read -r -a ARGV <<<"${SSH_ORIGINAL_COMMAND:-${*:-status}}"
VERB="${ARGV[0]:-status}"
FROM=${SSH_CLIENT:-local}; log "call from ${FROM%% *}: ${ARGV[*]}"

sha12() { [[ -f "$1" ]] && sha256sum "$1" | cut -c1-12 || echo ""; }
sig_ok() {  # $1 = config file; signature at $1.sig
  [[ -f "$1.sig" && -f $C/allowed_signers ]] || return 1
  ssh-keygen -Y verify -f $C/allowed_signers -I phoenix-config -n phoenix-mesh-config -s "$1.sig" < "$1" >/dev/null 2>&1
}
drift_of() {  # $1 = check command; prints drift items as a JSON array
  local out; out=$($1 check 2>/dev/null) && { echo "[]"; return; }
  python3 -c 'import json,sys; print(json.dumps([l.strip() for l in sys.stdin if l.startswith("  ")]))' <<<"$out"
}

status() {
  local active ip kgsha cursha tag hd sd smbd
  active=$(systemctl is-active nebula 2>/dev/null)
  ip=$(ip -4 -br addr show nebula1 2>/dev/null | awk '{print $3}')
  cursha=$(sha12 $C/config.yml); kgsha=$(sha12 $KG/config.yml)
  tag=$(cat $C/VERSION 2>/dev/null)
  if command -v phoenix-harden >/dev/null; then hd=$(drift_of phoenix-harden); else hd=null; fi
  if command -v phoenix-shares >/dev/null; then sd=$(drift_of phoenix-shares); smbd=$(systemctl is-active smbd 2>/dev/null); else sd=null; smbd=""; fi
  ACTIVE="$active" IP="$ip" CUR="$cursha" KGS="$kgsha" TAG="$tag" HD="$hd" SD="$sd" SMBD="$smbd" \
  KGSIG=$(sig_ok $KG/config.yml && echo true || echo false) \
  HT=$(systemctl is-active phoenix-mesh-heal.timer 2>/dev/null) \
  python3 - <<'PY'
import json, os, socket, time
e = os.environ
tag = e["TAG"]; want = tag.split("config:")[-1] if "config:" in tag else ""
mesh = {"active": e["ACTIVE"] == "active", "ip": e["IP"], "version": tag, "config_sha12": e["CUR"],
        "known_good_sha12": e["KGS"], "known_good_signed": e["KGSIG"] == "true", "heal_timer": e["HT"] == "active"}
mesh["config_matches_version"] = bool(want) and e["CUR"] == want
mesh["known_good_matches_version"] = bool(want) and e["KGS"] == want
hd = json.loads(e["HD"]); sd = json.loads(e["SD"])
shares = None if sd is None else {"smbd": e["SMBD"] == "active", "drift": sd}
problems = []
if not mesh["active"]: problems.append("mesh:down")
if not mesh["config_matches_version"]: problems.append("mesh:config-drift")
if not mesh["known_good_matches_version"]: problems.append("mesh:known-good-damaged")
if hd: problems += [f"harden:{d}" for d in hd]
if shares is not None:
    if not shares["smbd"]: problems.append("shares:smbd-down")
    problems += [f"shares:{d}" for d in sd]
print(json.dumps({"host": socket.gethostname(), "agent": "peer-agent-1.0.0", "time": int(time.time()),
                  "mesh": mesh, "harden": None if hd is None else {"drift": hd}, "shares": shares,
                  "problems": problems, "healthy": not problems}))
PY
}

case "$VERB" in
  status) status ;;
  heal)
    [[ -x /usr/local/sbin/phoenix-mesh-heal ]] && /usr/local/sbin/phoenix-mesh-heal >/dev/null 2>&1
    command -v phoenix-harden >/dev/null && phoenix-harden heal >/dev/null 2>&1
    command -v phoenix-shares >/dev/null && phoenix-shares heal >/dev/null 2>&1
    log "heal run on request"; sleep 3; status ;;
  export)
    [[ "${ARGV[1]:-}" == mesh ]] || { echo "export: only 'mesh'"; exit 2; }
    sig_ok $KG/config.yml || { echo "export refused: known-good is not signed" >&2; exit 3; }
    tar -C $KG -cf - config.yml config.yml.sig -C $C VERSION ;;
  restore)
    [[ "${ARGV[1]:-}" == mesh && "${ARGV[2]:-}" =~ ^[0-9a-f]{12}$ ]] || { echo "restore: mesh <12-hex config hash>"; exit 2; }
    want=${ARGV[2]}; t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
    head -c 1048576 | tar -C "$t" -xf - config.yml config.yml.sig VERSION 2>/dev/null || { log "restore refused: bad archive"; echo "bad archive"; exit 3; }
    [[ "$(sha12 "$t/config.yml")" == "$want" ]] || { log "restore refused: hash mismatch"; echo "hash mismatch"; exit 3; }
    sig_ok "$t/config.yml" || { log "restore refused: signature invalid"; echo "signature invalid"; exit 3; }
    grep -q "config:$want" "$t/VERSION" || { log "restore refused: VERSION does not name $want"; echo "version mismatch"; exit 3; }
    /usr/local/bin/nebula -test -config "$t/config.yml" >/dev/null 2>&1 || { log "restore refused: nebula -test failed"; echo "config test failed"; exit 3; }
    install -m 644 "$t/config.yml" "$t/config.yml.sig" $KG/
    install -m 644 "$t/config.yml" "$t/config.yml.sig" "$t/VERSION" $C/
    log "restored mesh config $want from a buddy (signature verified)"
    systemd-run --quiet --on-active=3 --unit="phoenix-peer-restart-$RANDOM" systemctl restart nebula
    echo "restored $want; nebula restarts in 3 s" ;;
  version) echo "$VERSION" ;;
  *) log "refused verb: $VERB"; echo "unknown verb"; exit 2 ;;
esac
