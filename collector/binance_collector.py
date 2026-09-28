#!/usr/bin/env python3
"""Binance USDT-M Futures piyasa verisi toplayıcı (sabah brifingi için).

Sadece herkese açık (public) endpoint'leri kullanır; API anahtarı gerekmez.
Her çalıştırmada her sembol için bir snapshot alır ve:
  - data/latest.json dosyasını günceller (brifingin okuduğu dosya)
  - data/snapshots.jsonl dosyasına satır ekler (yerel geçmiş)

Kullanım:
  python3 binance_collector.py                      # varsayılan semboller
  python3 binance_collector.py BTCUSDT ETHUSDT      # belirli semboller
  SYMBOLS=BTCUSDT,SOLUSDT python3 binance_collector.py
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
# Sabah brifingindeki büyük/stabil coin listesiyle aynı
DEFAULT_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "AVAXUSDT",
    "LINKUSDT", "DOTUSDT", "LTCUSDT", "BCHUSDT", "SUIUSDT",
]
RATIO_PERIOD = os.getenv("PERIOD", "4h")  # long/short ve taker oranları için
DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parent / "data"))
TIMEOUT = 10
RETRIES = 3


def get(path, params=None):
    url = f"{BASE_URL}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
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


def pct_change(new, old):
    if not old:
        return None
    return round((new - old) / old * 100, 2)


def last_float(rows, key):
    return float(rows[-1][key]) if rows else None


def snapshot(symbol, premium, ticker):
    # Son 25 saatlik saatlik OI geçmişi: güncel değer + 4s ve 24s değişim
    oi_hist = get("/futures/data/openInterestHist",
                  {"symbol": symbol, "period": "1h", "limit": 25})
    ratio_params = {"symbol": symbol, "period": RATIO_PERIOD, "limit": 1}
    global_ls = get("/futures/data/globalLongShortAccountRatio", ratio_params)
    top_ls = get("/futures/data/topLongShortPositionRatio", ratio_params)
    taker = get("/futures/data/takerlongshortRatio", ratio_params)

    oi_vals = [float(r["sumOpenInterestValue"]) for r in oi_hist]
    oi_now = oi_vals[-1] if oi_vals else None
    low, high = float(ticker["lowPrice"]), float(ticker["highPrice"])
    return {
        "symbol": symbol,
        "price": float(ticker["lastPrice"]),
        "mark_price": float(premium["markPrice"]),
        "change_24h_pct": float(ticker["priceChangePercent"]),
        "high_24h": high,
        "low_24h": low,
        "range_24h_pct": pct_change(high, low),
        "quote_volume_24h_usdt": round(float(ticker["quoteVolume"]), 0),
        "funding_rate_pct": round(float(premium["lastFundingRate"]) * 100, 4),
        "next_funding_time": datetime.fromtimestamp(
            premium["nextFundingTime"] / 1000, timezone.utc
        ).isoformat(timespec="minutes"),
        "oi_usdt": round(oi_now, 0) if oi_now else None,
        "oi_change_4h_pct": pct_change(oi_now, oi_vals[-5]) if len(oi_vals) >= 5 else None,
        "oi_change_24h_pct": pct_change(oi_now, oi_vals[0]) if len(oi_vals) >= 25 else None,
        "global_long_short_ratio": last_float(global_ls, "longShortRatio"),
        "global_long_pct": round(last_float(global_ls, "longAccount") * 100, 1) if global_ls else None,
        "top_trader_position_ls_ratio": last_float(top_ls, "longShortRatio"),
        "taker_buy_sell_ratio": last_float(taker, "buySellRatio"),
    }


def main():
    symbols = sys.argv[1:] or [
        s.strip().upper() for s in os.getenv("SYMBOLS", "").split(",") if s.strip()
    ] or DEFAULT_SYMBOLS
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    results, errors = [], {}
    try:
        # Tüm semboller için tek istekte
        premiums = {p["symbol"]: p for p in get("/fapi/v1/premiumIndex")}
        tickers = {t["symbol"]: t for t in get("/fapi/v1/ticker/24hr")}
    except Exception as e:
        premiums, tickers = {}, {}
        errors["*"] = str(e)

    if premiums:
        for sym in symbols:
            try:
                if sym not in premiums or sym not in tickers:
                    raise RuntimeError("sembol Binance Futures'ta bulunamadı")
                results.append(snapshot(sym, premiums[sym], tickers[sym]))
            except Exception as e:  # bir sembolün hatası diğerlerini durdurmasın
                errors[sym] = str(e)

    with open(DATA_DIR / "snapshots.jsonl", "a") as f:
        for row in results:
            f.write(json.dumps({"ts": ts, **row}) + "\n")

    latest = {
        "generated_at": ts,
        "source": "Binance USDT-M Futures (public API)",
        "ratio_period": RATIO_PERIOD,
        "coins": results,
        "errors": errors,
    }
    tmp = DATA_DIR / "latest.json.tmp"
    tmp.write_text(json.dumps(latest, indent=2, ensure_ascii=False))
    tmp.replace(DATA_DIR / "latest.json")

    for r in results:
        print(
            f"{r['symbol']:<9} {r['price']:>10g} {r['change_24h_pct']:+6.2f}% "
            f"funding={r['funding_rate_pct']:+.4f}% "
            f"OI={r['oi_usdt'] / 1e6:,.0f}M$ ({r['oi_change_24h_pct']}% 24s) "
            f"L/S={r['global_long_short_ratio']} top={r['top_trader_position_ls_ratio']} "
            f"taker={r['taker_buy_sell_ratio']}"
        )
    for sym, err in errors.items():
        print(f"{sym:<9} HATA: {err}", file=sys.stderr)
    return 1 if errors and not results else 0


if __name__ == "__main__":
    sys.exit(main())
