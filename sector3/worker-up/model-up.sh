#!/usr/bin/env bash
# model-up.sh — give H.L.K its local brain from what the box IMPORTED from
# Phoenix (no internet model library, no paid API — Jerry, 2026-09-29).
# Step 6 of "Phoenix from the cloud, a worker on the ground".
# Run as root:
#   model-up.sh <user> <workdir> <runtime-archive> <model-archive> <model-name>
#   e.g. model-up.sh a /srv/helix-ingress/phoenix-roadtest \
#          ollama-cpu-0.34.4-linux-amd64.tar.zst ollama-model-llama3.2-3b.tar llama3.2:3b
# Both archives must already be in <workdir>/ops (worker-bootstrap.sh … pulls
# and checks them against D1). Re-runnable: unpacks again only when the
# archive changed. Ollama listens on 127.0.0.1 only and keeps the model loaded
# (OLLAMA_KEEP_ALIVE=-1), so H.L.K never pays the load or the instruction
# read twice. H.L.K is switched to it through /etc/default/phoenix-hlk.
set -euo pipefail
U=${1:?user}; WD=${2:?workdir}; RT=${3:?runtime archive}; MA=${4:?model archive}; MODEL=${5:?model name}
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
say() { printf '  %-8s %s\n' "$1" "$2"; }
for f in "$RT" "$MA"; do [ -f "$WD/ops/$f" ] || { echo "$WD/ops/$f missing — pull it first"; exit 1; }; done
RUN="$WD/ollama"; MODELS="$WD/ollama-models"
install -d -o "$U" -g "$U" "$RUN" "$MODELS"

unpack() { # archive dest stamp-name [tar option]
  local arch="$WD/ops/$1" dest=$2 stamp="$2/.from-$3" sum
  sum=$(sha256sum "$arch" | cut -c1-64)
  if [ "$(cat "$stamp" 2>/dev/null)" = "$sum" ]; then say unpack "$1 unchanged"; return; fi
  sudo -u "$U" tar ${4:-} -xf "$arch" -C "$dest"
  echo "$sum" > "$stamp"; chown "$U:$U" "$stamp"
  say unpack "$1 -> $dest"
}
unpack "$RT" "$RUN" runtime --zstd
unpack "$MA" "$MODELS" model

cat > /etc/systemd/system/phoenix-ollama.service <<UNIT
# phoenix-ollama — H.L.K's local model runtime (CPU), imported from Phoenix.
# Written by sector3/worker-up/model-up.sh $(date -Is). Local-only: 127.0.0.1:11434.
[Unit]
Description=H.L.K local model runtime (Ollama, CPU, imported from Phoenix)
After=network.target helix@ingress.service
Before=phoenix-hlk.service

[Service]
User=$U
Environment=OLLAMA_HOST=127.0.0.1:11434
Environment=OLLAMA_MODELS=$MODELS
Environment=OLLAMA_KEEP_ALIVE=-1
Environment=OLLAMA_NOPRUNE=1
ExecStart=$RUN/bin/ollama serve
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable -q phoenix-ollama.service
systemctl restart phoenix-ollama.service
for i in $(seq 1 30); do curl -s -o /dev/null http://127.0.0.1:11434/api/tags && break; sleep 1; done
curl -s http://127.0.0.1:11434/api/tags | grep -q "\"$MODEL\"" || { echo "  model    $MODEL not visible to the runtime"; exit 1; }
say runtime "ollama $("$RUN/bin/ollama" --version 2>&1 | grep -o '[0-9][0-9.]*' | tail -1) on 127.0.0.1:11434, model $MODEL present"

# preload + pin in memory, so the first H.L.K request isn't a cold load
curl -s http://127.0.0.1:11434/api/generate -d "{\"model\":\"$MODEL\",\"prompt\":\"ok\",\"stream\":false,\"keep_alive\":-1,\"options\":{\"num_predict\":1}}" >/dev/null
say loaded "$MODEL pinned in memory"

cat > /etc/default/phoenix-hlk <<ENV
# H.L.K's model tier (read by phoenix-hlk.service). Written by model-up.sh.
HLK_MODEL=ollama
HLK_OLLAMA_URL=http://127.0.0.1:11434
HLK_OLLAMA_MODEL=$MODEL
ENV
systemctl restart phoenix-hlk.service 2>/dev/null && say hlk "switched to $MODEL (local)" || say hlk "phoenix-hlk not installed yet — run hlk-up.sh"
