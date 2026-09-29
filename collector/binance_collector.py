#!/usr/bin/env python3
"""Binance USDT-M Futures piyasa verisi toplayıcı (sabah brifingi için).

Sadece herkese açık (public) endpoint'leri kullanır; API anahtarı gerekmez.
Her çalıştırmada her sembol için bir snapshot alır ve:
  - data/latest.json dosyasını günceller (brifingin okuduğu dosya)
  - data/snapshots.jsonl dosyasına satır ekler (yerel geçmiş)

Özellik ve koşul hesapları features.py'dedir (backtest ile ortak).
data/backtest_summary.json varsa (backtest.py üretir), doğrulanmış koşullar
latest.json'a "evidence" olarak eklenir.

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import features as fx  # noqa: E402

BASE_URL = "https://fapi.binance.com"
SPOT_URL = "https://api.binance.com"
# Sabah brifingindeki büyük/stabil coin listesiyle aynı
DEFAULT_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT",
    "AVAXUSDT", "LINKUSDT", "LTCUSDT", "BCHUSDT", "SUIUSDT",
]
RATIO_PERIOD = os.getenv("PERIOD", "4h")  # taker_buy_sell_ratio alanı için
DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parent / "data"))
EVIDENCE_MAX_AGE_DAYS = 14
TIMEOUT = 10
RETRIES = 3


def get(path, params=None, base=BASE_URL):
    url = f"{base}{path}"
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


def parse_klines(rows, interval_ms, T):
    """API kline satırları → features bar tuple'ları; sadece T'den önce kapananlar."""
    return [
        (int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[7]), float(r[10]))
        for r in rows if int(r[0]) + interval_ms <= T
    ]


def premium_series(rows, T):
    """premiumIndexKlines → Series(kapanış zamanı, kapanış %); sadece T'ye kadar kapananlar."""
    return fx.Series((int(x[0]) + fx.HOUR, float(x[4]) * 100) for x in rows if int(x[0]) + fx.HOUR <= T)


def r(v, nd=2):
    return round(v, nd) if isinstance(v, (int, float)) else v


def snapshot(symbol, premium, ticker, T):
    # Son 200 saatlik OI geçmişi: güncel değer + 4s, 24s, 7g değişim
    oi_hist = get("/futures/data/openInterestHist",
                  {"symbol": symbol, "period": "1h", "limit": 200})
    ratio4h = {"symbol": symbol, "period": "4h", "limit": 180}  # 30 gün
    global_ls = get("/futures/data/globalLongShortAccountRatio", ratio4h)
    top_ls = get("/futures/data/topLongShortPositionRatio", ratio4h)
    taker = get("/futures/data/takerlongshortRatio",
                {"symbol": symbol, "period": RATIO_PERIOD, "limit": 1})
    warnings = []
    # Ek veriler: alınamazsa coin düşmez, temel alanlar yine yayınlanır
    try:
        k1h = get("/fapi/v1/klines", {"symbol": symbol, "interval": "1h", "limit": fx.N_1H + 1})
        k1d = get("/fapi/v1/klines", {"symbol": symbol, "interval": "1d", "limit": fx.N_1D + 1})
    except Exception as e:
        k1h, k1d = [], []
        warnings.append(f"klines: {e}")
    try:
        fund = get("/fapi/v1/fundingRate",
                   {"symbol": symbol, "startTime": T - 31 * fx.DAY, "limit": 1000})
    except Exception as e:
        fund = []
        warnings.append(f"funding geçmişi: {e}")
    try:
        spot_rows = get("/api/v3/klines", {"symbol": symbol, "interval": "1h", "limit": 30},
                        base=SPOT_URL)
    except Exception as e:  # spot verisi opsiyonel
        spot_rows = []
        warnings.append(f"spot: {e}")
    try:  # prim endeksi: 200 saat (7 günlük z-skoru için)
        prem_rows = get("/fapi/v1/premiumIndexKlines", {"symbol": symbol, "interval": "1h", "limit": 200})
    except Exception as e:
        prem_rows = []
        warnings.append(f"prim: {e}")

    oi_vals = [float(x["sumOpenInterestValue"]) for x in oi_hist]
    oi_now = oi_vals[-1] if oi_vals else None
    low, high = float(ticker["lowPrice"]), float(ticker["highPrice"])
    fund_recs = [(int(x["fundingTime"]), float(x["fundingRate"]), None) for x in fund]
    snap = {
        "symbol": symbol,
        "price": float(ticker["lastPrice"]),
        "mark_price": float(premium["markPrice"]),
        "basis_pct": round((float(premium["markPrice"]) / float(premium["indexPrice"]) - 1) * 100, 4)
        if float(premium.get("indexPrice") or 0) else None,
        "change_24h_pct": float(ticker["priceChangePercent"]),
        "high_24h": high,
        "low_24h": low,
        "range_24h_pct": pct_change(high, low),
        "quote_volume_24h_usdt": round(float(ticker["quoteVolume"]), 0),
        "funding_rate_pct": round(float(premium["lastFundingRate"]) * 100, 4),
        "funding_interval_h": fx.funding_interval_h(fund_recs),
        "next_funding_time": datetime.fromtimestamp(
            premium["nextFundingTime"] / 1000, timezone.utc
        ).isoformat(timespec="minutes"),
        "oi_usdt": round(oi_now, 0) if oi_now else None,
        "oi_change_4h_pct": pct_change(oi_now, oi_vals[-5]) if len(oi_vals) >= 5 else None,
        "oi_change_24h_pct": pct_change(oi_now, oi_vals[-25]) if len(oi_vals) >= 25 else None,
        "global_long_short_ratio": last_float(global_ls, "longShortRatio"),
        "global_long_pct": round(last_float(global_ls, "longAccount") * 100, 1) if global_ls else None,
        "top_trader_position_ls_ratio": last_float(top_ls, "longShortRatio"),
        "taker_buy_sell_ratio": last_float(taker, "buySellRatio"),
    }

    f = fx.compute_features(
        parse_klines(k1h, fx.HOUR, T)[-fx.N_1H:],
        parse_klines(k1d, fx.DAY, T)[-fx.N_1D:],
        T,
        spot=parse_klines(spot_rows, fx.HOUR, T),
        oi=fx.Series((int(x["timestamp"]), float(x["sumOpenInterestValue"])) for x in oi_hist),
        longp=fx.Series((int(x["timestamp"]), float(x["longAccount"]) * 100) for x in global_ls),
        top=fx.Series((int(x["timestamp"]), float(x["longShortRatio"])) for x in top_ls),
        funding=fx.funding_to_8h(fund_recs) if fund_recs else None,
        premium=premium_series(prem_rows, T) if prem_rows else None,
    )
    if f is None and k1h:
        warnings.append("özellikler hesaplanamadı (yetersiz mum)")
    return snap, f, warnings


def add_feature_fields(snap, f):
    """Brifingin kullandığı türetilmiş alanlar (yuvarlanmış)."""
    if not f:
        return
    snap.update({
        "ret_7d_pct": r(f["ret_7d"]),
        "ema20_1d": r(f.get("ema20_1d"), 6), "ema50_1d": r(f.get("ema50_1d"), 6),
        "ema200_1d": r(f.get("ema200_1d"), 6),
        "dist_ema50_1d_pct": r(f.get("dist_ema50_1d")),
        "dist_ema200_1d_pct": r(f.get("dist_ema200_1d")),
        "trend_4h": None if f.get("ema20_4h") is None or f.get("ema50_4h") is None
        else ("yukarı" if f["ema20_4h"] > f["ema50_4h"] else "aşağı"),
        "atr_pct_1d": r(f.get("atr_pct_1d")),
        "liq_distance_in_atr": r(f.get("liq_in_atr"), 1),
        "tp2_in_atr": r(f.get("tp2_in_atr")),
        "prev_day_high": f.get("prev_day_high"), "prev_day_low": f.get("prev_day_low"),
        "high_7d": f.get("high_7d"), "low_7d": f.get("low_7d"),
        "oi_change_7d_pct": r(f.get("oi_chg_7d")),
        "funding_8h_equiv_pct": r(f.get("funding_8h"), 4),
        "funding_pctl_30d": r(f.get("funding_pctl_30d"), 0),
        "funding_avg_7d_8h_pct": r(f.get("funding_avg_7d_8h"), 4),
        "global_long_pct_pctl_30d": r(f.get("long_pct_pctl_30d"), 0),
        "top_trader_ratio_pctl_30d": r(f.get("top_ratio_pctl_30d"), 0),
        "perp_taker_ratio_24h": r(f.get("perp_taker_ratio_24h"), 3),
        "spot_imbalance_24h": r(f.get("spot_imb_24h"), 3),
        "perp_imbalance_24h": r(f.get("perp_imb_24h"), 3),
        "spot_perp_volume_ratio": r(f.get("spot_perp_vol_ratio")),
        "premium_pct": r(f.get("premium_pct"), 4),
        "premium_z7d": r(f.get("premium_z7d")),
        "bbw_1d_pct": r(f.get("bbw_1d")),
        "bbw_pctl_90d": r(f.get("bbw_pctl_90d"), 0),
    })


def load_evidence(now):
    """backtest_summary.json'dan brifinge girecek özet. Yoksa/eskiyse None."""
    path = DATA_DIR / "backtest_summary.json"
    if not path.exists():
        return None
    try:
        s = json.loads(path.read_text(encoding="utf-8"))
        age = (now - datetime.fromisoformat(s["generated_at"])).total_seconds() / 86400
    except Exception as e:
        return {"status": f"okunamadı: {e}"}
    if age > EVIDENCE_MAX_AGE_DAYS:
        return {"status": f"eski ({age:.0f} gün)", "generated_at": s["generated_at"]}
    return {
        "status": "ok",
        "generated_at": s["generated_at"],
        "period": s["period"],
        "params": s["params"],
        "base": s["base"],
        "per_coin": s["per_coin"],
        "tested": s["tested"],
        "validated": s["validated"],
        "weak": [{k: c.get(k) for k in ("id", "desc_tr", "direction", "avg_pnl_true", "avg_pnl_false",
                                        "pnl_lift", "liq_rate_true", "liq_rate_false", "n_true")}
                 for c in s.get("weak", [])],
        "sl_summary": s.get("sl_summary"),
    }


def direction_summary(results):
    """Doğrulanmış kanıtı coin bazında tek bakışta okunur hâle getirir.

    long_favored / short_favored: o yön için PnL'i artıran doğrulanmış koşul aktif.
    long_weaker / short_weaker: o yön için PnL'i düşüren doğrulanmış koşul aktif.
    Her coin bir kovada en güçlü (|pnl_lift| en büyük) koşuluyla bir kez yer alır.
    no_evidence: hiçbir doğrulanmış koşulu aktif olmayan coinler.
    """
    out = {"long_favored": [], "short_favored": [], "long_weaker": [], "short_weaker": [], "no_evidence": []}
    for snap in results:
        hits = snap.get("evidence_hits") or []
        if not hits:
            out["no_evidence"].append(snap["symbol"].replace("USDT", ""))
            continue
        for d in ("long", "short"):
            for effect, bucket in (("olumlu", f"{d}_favored"), ("olumsuz", f"{d}_weaker")):
                hs = [h for h in hits if h["direction"] == d and h["effect"] == effect]
                if hs:
                    h = max(hs, key=lambda x: abs(x.get("pnl_lift") or 0))
                    out[bucket].append({"coin": snap["symbol"].replace("USDT", ""), **h})
    for k in ("long_favored", "short_favored", "long_weaker", "short_weaker"):
        out[k].sort(key=lambda x: -abs(x.get("pnl_lift") or 0))
    return out


def main():
    symbols = sys.argv[1:] or [
        s.strip().upper() for s in os.getenv("SYMBOLS", "").split(",") if s.strip()
    ] or DEFAULT_SYMBOLS
    now = datetime.now(timezone.utc)
    ts = now.isoformat(timespec="seconds")
    T = int(now.timestamp() * 1000) // fx.HOUR * fx.HOUR  # son saat başı
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    results, errors, feats, warns = [], {}, {}, {}
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
                snap, f, w = snapshot(sym, premiums[sym], tickers[sym], T)
                results.append(snap)
                feats[sym] = f
                if w:
                    warns[sym] = w
            except Exception as e:  # bir sembolün hatası diğerlerini durdurmasın
                errors[sym] = str(e)

    # BTC rejimi tüm coinlerin koşuluna girer
    btc = feats.get("BTCUSDT")
    btc_up = None
    if btc and btc.get("ema50_1d") is not None:
        btc_up = btc["price"] > btc["ema50_1d"]
    evidence = load_evidence(now)
    validated = (evidence or {}).get("validated", []) if (evidence or {}).get("status") == "ok" else []
    for snap in results:
        f = feats.get(snap["symbol"])
        add_feature_fields(snap, f)
        if snap["symbol"] in warns:
            snap["warnings"] = warns[snap["symbol"]]
        if f is None:
            snap["conditions_true"] = None
            continue
        f["btc_trend_up"] = btc_up
        conds = fx.evaluate_conditions(f)
        snap["conditions_true"] = sorted(k for k, v in conds.items() if v)
        snap["conditions_unknown"] = sorted(k for k, v in conds.items() if v is None)
        snap["evidence_hits"] = [
            {k: v.get(k) for k in ("id", "desc_tr", "direction", "effect", "rate_true", "rate_false",
                                   "avg_pnl_true", "avg_pnl_false", "pnl_lift", "n_true",
                                   "liq_rate_true", "liq_rate_false")}
            for v in validated if conds.get(v["id"])
        ]

    with open(DATA_DIR / "snapshots.jsonl", "a", encoding="utf-8") as fh:
        for row in results:
            fh.write(json.dumps({"ts": ts, **row}) + "\n")

    latest = {
        "generated_at": ts,
        "feature_time": datetime.fromtimestamp(T / 1000, timezone.utc).isoformat(timespec="minutes"),
        "source": "Binance USDT-M Futures (public API)",
        "ratio_period": RATIO_PERIOD,
        "btc_trend_up_1d": btc_up,
        "coins": results,
        "errors": errors,
        "evidence": evidence,
        "direction_summary": direction_summary(results) if (evidence or {}).get("status") == "ok" else None,
    }
    tmp = DATA_DIR / "latest.json.tmp"
    tmp.write_text(json.dumps(latest, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(DATA_DIR / "latest.json")

    for s in results:
        print(
            f"{s['symbol']:<9} {s['price']:>10g} {s['change_24h_pct']:+6.2f}% "
            f"funding={s['funding_rate_pct']:+.4f}% (p{s.get('funding_pctl_30d')}) "
            f"OI={s['oi_usdt'] / 1e6:,.0f}M$ ({s['oi_change_24h_pct']}% 24s) "
            f"long%={s['global_long_pct']} (p{s.get('global_long_pct_pctl_30d')}) "
            f"ATR={s.get('atr_pct_1d')}% trend4h={s.get('trend_4h')} "
            f"koşul={len(s.get('conditions_true') or [])} kanıt={len(s.get('evidence_hits') or [])}"
        )
    for sym, err in errors.items():
        print(f"{sym:<9} HATA: {err}", file=sys.stderr)
    for sym, w in warns.items():
        print(f"{sym:<9} UYARI: {'; '.join(w)}", file=sys.stderr)
    if evidence:
        print(f"kanıt: {evidence.get('status')}, doğrulanmış koşul={len(validated)}")
    return 1 if errors and not results else 0


if __name__ == "__main__":
    sys.exit(main())
