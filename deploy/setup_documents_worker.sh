#!/usr/bin/env bash
# setup_documents_worker.sh — Deploy documents-worker to Cloudflare
# Run from WSL as regular user (not sudo)
#
# Prerequisites: wrangler installed, wrangler login complete
# Usage: bash ~/phoenix-devops/deploy/setup_documents_worker.sh

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKER_DIR="$REPO/sector2/documents-worker"

echo "[documents-worker] Deploying from: $WORKER_DIR"
cd "$WORKER_DIR"

# 1. Create R2 bucket (idempotent — ok if already exists)
echo "[1/5] Creating R2 bucket phoenix-docs..."
wrangler r2 bucket create phoenix-docs 2>/dev/null || echo "       (bucket may already exist — continuing)"

# 2. Apply D1 schema
echo "[2/5] Applying D1 schema to phoenix_dev_db..."
wrangler d1 execute phoenix_dev_db --remote --file=schema.sql

# 3. Set secrets
echo "[3/5] Setting secrets..."
echo "      → PHOENIX_AUTH (paste your token, press Enter):"
wrangler secret put PHOENIX_AUTH

echo "      → OWNER_TOKENS (paste JSON like {\"jwl247\":\"tok\",\"laurie\":\"tok\"}, press Enter):"
wrangler secret put OWNER_TOKENS

# 4. Deploy worker
echo "[4/5] Deploying worker..."
wrangler deploy

# 5. Done
echo ""
echo "=== documents-worker LIVE ==="
echo "  Worker:  https://documents-worker.phoenix-jwl.workers.dev"
echo "  Status:  https://documents-worker.phoenix-jwl.workers.dev/status"
echo ""
echo "Next: deploy conversion_agent on phoenix-ext"
echo "  sudo bash $REPO/deploy/setup_conversion_agent.sh"
