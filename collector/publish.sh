#!/usr/bin/env bash
# Veriyi toplar ve latest.json'ı GitHub'daki `market-data` branch'ine yayınlar.
# Branch her seferinde tek commit olarak yeniden yazılır (geçmiş şişmez);
# yerel geçmiş VPS'te data/snapshots.jsonl içinde kalır.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PUB_DIR="${PUB_DIR:-/opt/kripto-brifing-publish}"
DEPLOY_KEY="${DEPLOY_KEY:-$HOME/.ssh/kripto_brifing_deploy}"
REMOTE="${REMOTE:-git@github.com:doruq-IT/kripto-brifing.git}"

/usr/bin/python3 "$REPO_DIR/collector/binance_collector.py"

rm -rf "$PUB_DIR"
mkdir -p "$PUB_DIR"
cp "$REPO_DIR/collector/data/latest.json" "$PUB_DIR/latest.json"
cd "$PUB_DIR"
git init -q -b market-data
git add latest.json
git -c user.name="kripto-brifing-bot" -c user.email="bot@okan-vps" \
    commit -qm "Market data $(date -u +%Y-%m-%dT%H:%MZ)"
GIT_SSH_COMMAND="ssh -i $DEPLOY_KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new" \
    git push -qf "$REMOTE" market-data
echo "yayınlandı: $(date -u +%H:%MZ)"
