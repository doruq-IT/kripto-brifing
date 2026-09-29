#!/usr/bin/env bash
# Haftalık: geçmiş veriyi günceller ve backtest'i çalıştırır.
# Sonuç (data/backtest_summary.json) bir sonraki saatlik publish.sh ile latest.json'a girer.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
export DAYS="${DAYS:-730}"  # 2 yıl; history_download ve backtest aynı süreyi kullanır
/usr/bin/python3 "$DIR/history_download.py"
/usr/bin/python3 "$DIR/backtest.py" > /dev/null
sed -n '1,2p;/^3) DOĞRULANMIŞ/,/^$/p;/^3b) ZAYIF/,/^$/p' "$DIR/data/backtest_report.txt"
echo "backtest bitti: $(date -u +%Y-%m-%dT%H:%MZ)"
