#!/usr/bin/env python3
"""Binance USDT-M Futures piyasa verisi toplayıcı.

Sadece herkese açık (public) endpoint'leri kullanır; API anahtarı gerekmez.
Her çalıştırmada her sembol için tek bir snapshot alır ve:
  - data/snapshots.jsonl dosyasına bir satır ekler (geçmiş)
  - data/latest.json dosyasını günceller (son durum)

Kullanım:
  python3 binance_collector.py                      # varsayılan semboller
  python3 binance_collector.py BTCUSDT ETHUSDT      # belirli semboller
  SYMBOLS=BTCUSDT,SOLUSDT PERIOD=1h python3 binance_collector.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = "https://fapi.binance.com"
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
PERIOD = os.getenv("PERIOD", "4h")  # 5m,15m,30m,1h,2h,4h,6h,12h,1d
DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parent / "data"))
TIMEOUT = 10
RETRIES = 3


def get(path, params):
    url = f"{BASE_URL}{path}?{urllib.parse.urlencode(params)}"
    last_err = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            # 4xx (451 dahil) tekrar denemekle düzelmez
            if 400 <= e.code < 500:
                raise RuntimeError(f"HTTP {e.code} {path}: {e.read().decode()[:200]}")
            last_err = e
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
        time.sleep(2 ** attempt)
    raise RuntimeError(f"{path} başarısız: {last_err}")


def snapshot(symbol):
    premium = get("/fapi/v1/premiumIndex", {"symbol": symbol})
    oi = get("/fapi/v1/openInterest", {"symbol": symbol})
    ls = get(
        "/futures/data/globalLongShortAccountRatio",
        {"symbol": symbol, "period": PERIOD, "limit": 1},
    )
    ls_last = ls[-1] if ls else {}
    mark = float(premium["markPrice"])
    oi_qty = float(oi["openInterest"])
    return {
        "symbol": symbol,
        "mark_price": mark,
        "index_price": float(premium["indexPrice"]),
        "funding_rate": float(premium["lastFundingRate"]),
        "next_funding_time": premium["nextFundingTime"],
        "open_interest": oi_qty,
        "open_interest_usdt": round(oi_qty * mark, 2),
        "long_short_ratio": float(ls_last["longShortRatio"]) if ls_last else None,
        "long_account": float(ls_last["longAccount"]) if ls_last else None,
        "short_account": float(ls_last["shortAccount"]) if ls_last else None,
        "ls_period": PERIOD,
    }


def main():
    symbols = sys.argv[1:] or [
        s.strip().upper() for s in os.getenv("SYMBOLS", "").split(",") if s.strip()
    ] or DEFAULT_SYMBOLS
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    results, errors = [], {}
    for sym in symbols:
        try:
            results.append({"ts": ts, **snapshot(sym)})
        except Exception as e:  # bir sembolün hatası diğerlerini durdurmasın
            errors[sym] = str(e)

    with open(DATA_DIR / "snapshots.jsonl", "a") as f:
        for row in results:
            f.write(json.dumps(row) + "\n")

    latest = {"ts": ts, "data": results, "errors": errors}
    tmp = DATA_DIR / "latest.json.tmp"
    tmp.write_text(json.dumps(latest, indent=2))
    tmp.replace(DATA_DIR / "latest.json")

    for row in results:
        print(
            f"{row['symbol']:<10} mark={row['mark_price']:.2f} "
            f"funding={row['funding_rate'] * 100:.4f}% "
            f"OI={row['open_interest_usdt'] / 1e6:.1f}M$ "
            f"L/S={row['long_short_ratio']}"
        )
    for sym, err in errors.items():
        print(f"{sym:<10} HATA: {err}", file=sys.stderr)
    return 1 if errors and not results else 0


if __name__ == "__main__":
    sys.exit(main())
