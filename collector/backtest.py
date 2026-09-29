#!/usr/bin/env python3
"""Okan'ın işlem kurgusunu geçmiş veride simüle eder ve koşulların etkisini ölçer.

Kurgu (ortam değişkenleriyle değiştirilebilir):
  - Her coin için STEP_H (4) saatte bir özellikler hesaplanır; saatler FEATURE_HOUR'dan
    (05:00 UTC, brifingin okuduğu an) başlar: 01, 05, 09, 13, 17, 21 UTC. Bir sonraki
    saatin açılışında (ENTRY_HOUR − FEATURE_HOUR = 1 saat sonra) long ve short için ayrı
    ayrı sanal işlem açılır. Saatlik durum motoru her saat çalıştığı için tek sabah
    saati yerine günün farklı saatleri örneklenir. STEP_H=24 eski günlük kurguyu verir.
  - TP: +%2 fiyat. SL yok. Liq: -%19,5 (5x isolated). En fazla HOLD_H (96) saat.
  - Aynı saatlik mumda hem TP hem ters seviye görülürse ters seviye önce sayılır
    (muhafazakâr varsayım; mum içi sıra bilinmiyor).
  - "Temiz kazanç" = fiyat TP'ye, ters yönde %10'a (ekleme bölgesi) hiç
    gitmeden ulaştı. Ana başarı ölçütü budur.
  - PnL (eklemesiz): TP → +notional×%2; liq → -marj; süre dolarsa kapanıştan.
    İki yönlü %0,05 taker ücreti ve tutma süresindeki funding ödemeleri dahil.

İstatistik:
  - Her koşul için: koşul doğruyken ve yanlışken işlem başı ortalama PnL ve
    temiz kazanç oranı. Doğrulama PnL farkına göre yapılır; temiz kazanç tek
    başına yanıltıcıdır (oynaklık iki yönde de TP'yi hızlandırır ama liq'i artırır).
  - Güven aralığı: haftalık blok bootstrap (coinler aynı gün, işlemler ardışık
    günlerde birbirine bağımlı olduğu için hafta bazında yeniden örnekleme).
  - Çoklu test: aralık düzeyi test sayısından hesaplanır (Bonferroni): 100 − 5/test sayısı.
    38 koşul × 2 yön = 76 test → %99,93. Uç kuyruğu sağlıklı ölçmek için BOOT 10.000.
  - "Doğrulanmış" = PnL farkının aralığı sıfırı içermiyor + iki yarıda da aynı yön
    + koşulun doğru olduğu en az MIN_N işlem (günlük 60'ın STEP_H'ye göre ölçeklisi)
    ve 30 farklı gün.

Çıktı: data/backtest_summary.json (collector okur), data/backtest_report.txt
"""
import csv
import json
import os
import random
import statistics
import sys
from bisect import bisect_left
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import features as fx  # noqa: E402
from binance_collector import DEFAULT_SYMBOLS  # noqa: E402

HOUR, DAY = fx.HOUR, fx.DAY
T_, O_, H_, L_, C_ = 0, 1, 2, 3, 4

P = {
    "tp_pct": float(os.getenv("TP_PCT", "2")),
    "adverse_pct": float(os.getenv("ADV_PCT", "10")),
    "liq_pct": float(os.getenv("LIQ_PCT", str(fx.LIQ_DISTANCE_PCT))),
    "hold_h": int(os.getenv("HOLD_H", "96")),
    "margin_usdt": float(os.getenv("MARGIN", "50")),
    "leverage": float(os.getenv("LEV", "5")),
    "fee_pct": float(os.getenv("FEE_PCT", "0.05")),
    "feature_hour_utc": int(os.getenv("FEATURE_HOUR", "5")),
    "entry_hour_utc": int(os.getenv("ENTRY_HOUR", "6")),
    "step_h": int(os.getenv("STEP_H", "4")),
    "days": int(os.getenv("DAYS", "365")),
    "bootstrap": int(os.getenv("BOOT", "10000")),
    # Bonferroni: 100 − 5 / test sayısı (koşul × 2 yön); CI_LEVEL ile sabitlenebilir
    "ci_level_pct": float(os.getenv("CI_LEVEL") or round(100 - 5 / (2 * len(fx.CONDITIONS)), 3)),
    "min_n": int(os.getenv("MIN_N", "0")),  # 0 → 60 × 24 / STEP_H (aşağıda)
    # SL karşılaştırması: fiyat yüzdesi (5x'te ROE = 5 katı). Stop piyasa emriyle kapanır → kayma payı.
    "sl_grid": [float(x) for x in os.getenv("SL_GRID", "2,3,5,8,10").split(",") if x],
    "sl_slippage_pct": float(os.getenv("SL_SLIP", "0.05")),
}
P["min_n"] = P["min_n"] or 60 * 24 // P["step_h"]
HIST_DIR = Path(os.getenv("HIST_DIR", HERE / "data" / "history"))
DATA_DIR = Path(os.getenv("DATA_DIR", HERE / "data"))


def read_rows(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.reader(f))[1:]


def load_symbol(sym):
    d = HIST_DIR / sym
    fut = [(int(r[0]), *map(float, r[1:7])) for r in read_rows(d / "fut_1h.csv")]
    spot = [(int(r[0]), *map(float, r[1:7])) for r in read_rows(d / "spot_1h.csv")]
    fund_raw = [(int(r[0]), float(r[1])) for r in read_rows(d / "funding.csv")]
    met = [(int(r[0]), float(r[1]), float(r[2]), float(r[3])) for r in read_rows(d / "metrics.csv")]
    prem = [(int(r[0]) + HOUR, float(r[1]) * 100) for r in read_rows(d / "premium_1h.csv")]
    daily = fx.resample(fut, 24)
    return {
        "fut": fut,
        "fut_idx": {b[0]: i for i, b in enumerate(fut)},
        "daily": daily,
        "daily_t": [b[0] for b in daily],
        "spot": spot,
        "spot_idx": {b[0]: i for i, b in enumerate(spot)},
        "fund_raw_t": [t for t, _ in fund_raw],
        "fund_raw": fund_raw,
        "funding": fx.funding_to_8h([(t, r, None) for t, r in fund_raw]),
        "oi": fx.Series((m[0], m[1]) for m in met) if met else None,
        "longp": fx.Series((m[0], m[2]) for m in met) if met else None,
        "top": fx.Series((m[0], m[3]) for m in met) if met else None,
        "premium": fx.Series(prem) if prem else None,
    }


def simulate(s, i, d, sl=None):
    """i: giriş mumu indeksi, d: +1 long / -1 short, sl: stop (fiyat %, None = stop yok).

    Aynı mumda stop ve TP birlikte görülürse stop önce sayılır (kötümser). Pencere eksikse None.
    """
    bars = s["fut"]
    hold = P["hold_h"]
    if i + hold > len(bars):
        return None
    e = bars[i][O_]
    tp = e * (1 + d * P["tp_pct"] / 100)
    adv = e * (1 - d * P["adverse_pct"] / 100)
    liq = e * (1 - d * P["liq_pct"] / 100)
    stop = e * (1 - d * sl / 100) if sl is not None and sl < P["liq_pct"] else None
    pain, res, j = False, "timeout", i + hold - 1
    for j in range(i, i + hold):
        b = bars[j]
        if d == 1:
            hit_adv, hit_liq, hit_tp = b[L_] <= adv, b[L_] <= liq, b[H_] >= tp
        else:
            hit_adv, hit_liq, hit_tp = b[H_] >= adv, b[H_] >= liq, b[L_] <= tp
        pain = pain or hit_adv
        if hit_liq and stop is None:
            res = "liq"
            break
        if stop is not None and (b[L_] <= stop if d == 1 else b[H_] >= stop):
            res = "sl"
            break
        if hit_tp:
            res = "tp"
            break
    notional = P["margin_usdt"] * P["leverage"]
    fee = 2 * notional * P["fee_pct"] / 100
    entry_t, exit_t = bars[i][T_], bars[j][T_] + HOUR
    if res == "liq":
        pnl = -P["margin_usdt"]
    else:
        if res == "tp":
            move = P["tp_pct"] / 100
        elif res == "sl":
            move = -(sl + P["sl_slippage_pct"]) / 100
        else:
            move = d * (bars[j][C_] / e - 1)
        pnl = notional * move - fee
        a = bisect_left(s["fund_raw_t"], entry_t + 1)
        b_ = bisect_left(s["fund_raw_t"], exit_t + 1)
        pnl -= d * notional * sum(r for _, r in s["fund_raw"][a:b_])
    return {
        "res": res,
        "clean": res == "tp" and not pain,
        "pain": pain,
        "pnl": pnl,
        "hours": (exit_t - entry_t) / HOUR,
    }


def build_trades(data):
    trades = []
    btc = data.get("BTCUSDT")
    for sym, s in data.items():
        fut, daily = s["fut"], s["daily"]
        if len(fut) < 1000:
            print(f"{sym}: yetersiz mum ({len(fut)})", file=sys.stderr)
            continue
        daily_t = s["daily_t"]
        first_day = fut[0][0] // DAY * DAY + 42 * DAY  # 1000 saatlik pencere için
        last_day = fut[-1][0] // DAY * DAY
        start_day = max(first_day, last_day - P["days"] * DAY)
        step = P["step_h"]
        hours = [h for h in range(24) if (h - P["feature_hour_utc"]) % step == 0]
        entry_off = (P["entry_hour_utc"] - P["feature_hour_utc"]) * HOUR
        for T in (day + h * HOUR for day in range(start_day, last_day + DAY, DAY) for h in hours):
            day = T // DAY * DAY
            iT = s["fut_idx"].get(T)
            iE = s["fut_idx"].get(T + entry_off)
            if iT is None or iE is None:
                continue
            jd = bisect_left(daily_t, T - DAY + 1)  # t + DAY <= T olan günlük barlar
            js = s["spot_idx"].get(T)
            f = fx.compute_features(
                fut[max(0, iT - fx.N_1H):iT], daily[max(0, jd - fx.N_1D):jd], T,
                spot=s["spot"][max(0, js - 30):js] if js else None,
                oi=s["oi"], longp=s["longp"], top=s["top"], funding=s["funding"],
                premium=s.get("premium"),
            )
            if f is None:
                continue
            f["btc_trend_up"] = btc_trend(btc, T)
            conds = fx.evaluate_conditions(f)
            date = datetime.fromtimestamp(day / 1000, timezone.utc).date()
            for d, name in ((1, "long"), (-1, "short")):
                out = simulate(s, iE, d)
                if out is None:
                    continue
                out["sl"] = {}
                for sl in P["sl_grid"]:
                    o = simulate(s, iE, d, sl)
                    out["sl"][sl] = (o["res"], o["pnl"])
                out.update(sym=sym, dir=name, date=date.isoformat(),
                           week="%d-%02d" % date.isocalendar()[:2], conds=conds)
                trades.append(out)
    return trades


_btc_cache = {}


def btc_trend(btc, T):
    if btc is None:
        return None
    if T not in _btc_cache:
        daily = btc["daily"]
        jd = bisect_left(btc["daily_t"], T - DAY + 1)
        e = fx.ema([b[C_] for b in daily[max(0, jd - fx.N_1D):jd]], 50)
        iT = btc["fut_idx"].get(T)
        _btc_cache[T] = None if e is None or not iT else btc["fut"][iT - 1][C_] > e
    return _btc_cache[T]


def stats(ts):
    n = len(ts)
    if not n:
        return {"n": 0}
    wins = [t["pnl"] for t in ts if t["res"] == "tp"]
    losses = [-t["pnl"] for t in ts if t["res"] != "tp" and t["pnl"] < 0]
    avg_w = statistics.mean(wins) if wins else None
    avg_l = statistics.mean(losses) if losses else None
    tp_h = [t["hours"] for t in ts if t["res"] == "tp"]
    return {
        "n": n,
        "clean_rate": round(100 * sum(t["clean"] for t in ts) / n, 2),
        "tp_rate": round(100 * sum(t["res"] == "tp" for t in ts) / n, 2),
        "liq_rate": round(100 * sum(t["res"] == "liq" for t in ts) / n, 2),
        "pain_rate": round(100 * sum(t["pain"] for t in ts) / n, 2),
        "timeout_rate": round(100 * sum(t["res"] == "timeout" for t in ts) / n, 2),
        "avg_pnl_usdt": round(statistics.mean(t["pnl"] for t in ts), 3),
        "total_pnl_usdt": round(sum(t["pnl"] for t in ts), 1),
        "median_hours_to_tp": round(statistics.median(tp_h), 1) if tp_h else None,
        "breakeven_tp_rate": round(100 * avg_l / (avg_w + avg_l), 2) if avg_w and avg_l else None,
    }


def rate(w, n):
    return 100 * w / n if n else None


def test_condition(ts, cid, weeks, mid_date, rng):
    """Koşul doğru/yanlış karşılaştırması.

    Doğrulama ölçütü işlem başı ortalama PnL farkıdır (Okan'ın gerçekte kazandığı).
    Temiz kazanç oranı farkı da raporlanır ama tek başına kanıt sayılmaz: yüksek
    oynaklık %2'ye her iki yönde de daha sık ulaştırır, fakat liq'i de artırır.
    """
    A = [t for t in ts if t["conds"].get(cid) is True]
    B = [t for t in ts if t["conds"].get(cid) is False]
    res = {"n_true": len(A), "n_false": len(B), "days_true": len({t["date"] for t in A})}
    if not A or not B:
        return res
    pA = rate(sum(t["clean"] for t in A), len(A))
    pB = rate(sum(t["clean"] for t in B), len(B))
    lift = pA - pB
    sa, sb = stats(A), stats(B)
    pnl_lift = sa["avg_pnl_usdt"] - sb["avg_pnl_usdt"]
    # hafta başına: [temizA, nA, temizB, nB, pnlA, pnlB]
    per = {w: [0, 0, 0, 0, 0.0, 0.0] for w in weeks}
    for t in A:
        x = per[t["week"]]
        x[0] += t["clean"]; x[1] += 1; x[4] += t["pnl"]
    for t in B:
        x = per[t["week"]]
        x[2] += t["clean"]; x[3] += 1; x[5] += t["pnl"]
    rows = [per[w] for w in weeks]
    lifts, pnl_lifts = [], []
    for _ in range(P["bootstrap"]):
        wa = na = wb = nb = 0
        qa = qb = 0.0
        for _ in range(len(rows)):
            x = rows[rng.randrange(len(rows))]
            wa += x[0]; na += x[1]; wb += x[2]; nb += x[3]; qa += x[4]; qb += x[5]
        if na and nb:
            lifts.append(100 * (wa / na - wb / nb))
            pnl_lifts.append(qa / na - qb / nb)
    tail = (100 - P["ci_level_pct"]) / 200

    def ci(v):
        if not v:
            return None, None
        v.sort()
        return v[int(tail * len(v))], v[min(len(v) - 1, int((1 - tail) * len(v)))]

    lo, hi = ci(lifts)
    plo, phi = ci(pnl_lifts)

    def half(pred):
        a = [t for t in A if pred(t["date"])]
        b = [t for t in B if pred(t["date"])]
        if not a or not b:
            return None, None
        return (rate(sum(t["clean"] for t in a), len(a)) - rate(sum(t["clean"] for t in b), len(b)),
                statistics.mean(t["pnl"] for t in a) - statistics.mean(t["pnl"] for t in b))

    (h1, ph1), (h2, ph2) = half(lambda x: x < mid_date), half(lambda x: x >= mid_date)
    r2 = lambda v: round(v, 2) if v is not None else None  # noqa: E731
    res.update({
        "rate_true": round(pA, 2), "rate_false": round(pB, 2), "lift_pp": round(lift, 2),
        "ci_low": r2(lo), "ci_high": r2(hi), "half1_lift": r2(h1), "half2_lift": r2(h2),
        "liq_rate_true": sa["liq_rate"], "liq_rate_false": sb["liq_rate"],
        "avg_pnl_true": sa["avg_pnl_usdt"], "avg_pnl_false": sb["avg_pnl_usdt"],
        "pnl_lift": round(pnl_lift, 3), "pnl_ci_low": r2(plo), "pnl_ci_high": r2(phi),
        "pnl_half1": r2(ph1), "pnl_half2": r2(ph2),
    })
    same_sign = ph1 is not None and ph2 is not None and ph1 * pnl_lift > 0 and ph2 * pnl_lift > 0
    excl_zero = plo is not None and (plo > 0 or phi < 0)
    res["validated"] = bool(
        len(A) >= P["min_n"] and len(B) >= P["min_n"] and res["days_true"] >= 30
        and excl_zero and same_sign and len(weeks) >= 20
    )
    return res


def sl_analysis(ts, weeks, mid_date, rng, boot=1000):
    """Aynı işlemlerde stop yok ve her stop seviyesi. Fark eşleştirilmiş (aynı işlem), haftalık bootstrap %95."""
    if not ts:
        return []

    def pnl(t, sl):
        return t["pnl"] if sl is None else t["sl"][sl][1]

    def res(t, sl):
        return t["res"] if sl is None else t["sl"][sl][0]

    out = []
    n = len(ts)
    for sl in [None] + P["sl_grid"]:
        row = {
            "sl_pct": sl, "n": n,
            "tp_rate": round(100 * sum(res(t, sl) == "tp" for t in ts) / n, 2),
            "sl_rate": round(100 * sum(res(t, sl) == "sl" for t in ts) / n, 2),
            "liq_rate": round(100 * sum(res(t, sl) == "liq" for t in ts) / n, 2),
            "avg_pnl_usdt": round(sum(pnl(t, sl) for t in ts) / n, 3),
            "total_pnl_usdt": round(sum(pnl(t, sl) for t in ts), 1),
            "worst_trade_usdt": round(min(pnl(t, sl) for t in ts), 2),
        }
        if sl is not None:
            per = {w: [0.0, 0] for w in weeks}
            for t in ts:
                per[t["week"]][0] += pnl(t, sl) - t["pnl"]
                per[t["week"]][1] += 1
            rows = [v for v in per.values() if v[1]]
            diffs = []
            for _ in range(boot):
                q = c = 0
                for _ in range(len(rows)):
                    x = rows[rng.randrange(len(rows))]
                    q += x[0]; c += x[1]
                if c:
                    diffs.append(q / c)
            diffs.sort()
            h = [sum(pnl(t, sl) - t["pnl"] for t in ts if pred(t["date"])) /
                 max(1, sum(1 for t in ts if pred(t["date"])))
                 for pred in (lambda x: x < mid_date, lambda x: x >= mid_date)]
            d = row["avg_pnl_usdt"] - round(sum(t["pnl"] for t in ts) / n, 3)
            lo, hi = diffs[int(0.025 * len(diffs))], diffs[int(0.975 * len(diffs)) - 1]
            row.update(diff_vs_none=round(d, 3), ci_low=round(lo, 3), ci_high=round(hi, 3),
                       half1=round(h[0], 3), half2=round(h[1], 3),
                       significant=bool((lo > 0 or hi < 0) and h[0] * d > 0 and h[1] * d > 0))
        out.append(row)
    return out


def sl_verdict(rows):
    """En yüksek ortalama PnL'li seçenek; stop yoktan anlamlı farklı değilse 'kanıt yok'."""
    if not rows:
        return None
    none = rows[0]
    best = max(rows, key=lambda r: r["avg_pnl_usdt"])
    return {
        "best_sl_pct": best["sl_pct"], "best_avg_pnl": best["avg_pnl_usdt"],
        "none_avg_pnl": none["avg_pnl_usdt"],
        "significant": bool(best["sl_pct"] is not None and best.get("significant")),
        "sl5_avg_pnl": next((r["avg_pnl_usdt"] for r in rows if r["sl_pct"] == 5), None),
    }


def fmt(v, suffix="", nd=1):
    return "—" if v is None else f"{v:.{nd}f}{suffix}"


def main():
    symbols = [s.strip().upper() for s in os.getenv("SYMBOLS", "").split(",") if s.strip()] \
        or DEFAULT_SYMBOLS
    data = {}
    for sym in symbols:
        s = load_symbol(sym)
        if s["fut"]:
            data[sym] = s
        else:
            print(f"{sym}: geçmiş veri yok (önce history_download.py)", file=sys.stderr)
    if not data:
        return 1
    trades = build_trades(data)
    if not trades:
        print("Hiç işlem üretilemedi (veri yetersiz).", file=sys.stderr)
        return 1

    rng = random.Random(42)
    dates = sorted({t["date"] for t in trades})
    mid = dates[len(dates) // 2]
    weeks = sorted({t["week"] for t in trades})
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "period": {"start": dates[0], "end": dates[-1], "days": len(dates), "weeks": len(weeks)},
        "params": P,
        "coins": sorted(data),
        "base": {}, "per_coin": {}, "conditions": [], "validated": [],
    }
    for dname in ("long", "short"):
        ts = [t for t in trades if t["dir"] == dname]
        summary["base"][dname] = stats(ts)
        for sym in sorted(data):
            summary["per_coin"].setdefault(sym, {})[dname] = stats([t for t in ts if t["sym"] == sym])
        for cid, desc, _ in fx.CONDITIONS:
            r = test_condition(ts, cid, weeks, mid, rng)
            r.update(id=cid, desc_tr=desc, direction=dname)
            if "pnl_lift" in r:
                r["effect"] = "olumlu" if r["pnl_lift"] > 0 else "olumsuz"
            summary["conditions"].append(r)
    summary["tested"] = sum(1 for c in summary["conditions"] if "lift_pp" in c)
    summary["validated"] = [c for c in summary["conditions"] if c.get("validated")]
    summary["sl_analysis"] = {"base": {}, "validated": {}}
    summary["sl_summary"] = {}
    for dname in ("long", "short"):
        ts = [t for t in trades if t["dir"] == dname]
        rows = sl_analysis(ts, weeks, mid, rng)
        summary["sl_analysis"]["base"][dname] = rows
        summary["sl_summary"][dname] = sl_verdict(rows)
    for c in summary["validated"]:
        ts = [t for t in trades if t["dir"] == c["direction"] and t["conds"].get(c["id"]) is True]
        key = f"{c['id']}|{c['direction']}"
        rows = sl_analysis(ts, weeks, mid, rng)
        summary["sl_analysis"]["validated"][key] = rows
        summary["sl_summary"][key] = sl_verdict(rows)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "backtest_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                                                    encoding="utf-8")
    report = render_report(summary)
    (DATA_DIR / "backtest_report.txt").write_text(report, encoding="utf-8")
    print(report)
    return 0


def render_report(s):
    p = s["params"]
    L = []
    L.append(f"BACKTEST RAPORU — {s['generated_at']}")
    L.append(f"Dönem: {s['period']['start']} → {s['period']['end']} "
             f"({s['period']['days']} gün, {s['period']['weeks']} hafta), coinler: {', '.join(s['coins'])}")
    hrs = [(h + p['entry_hour_utc'] - p['feature_hour_utc']) % 24 for h in range(24)
           if (h - p['feature_hour_utc']) % p.get('step_h', 24) == 0]
    L.append(f"Kurgu: giriş {', '.join(f'{h:02d}' for h in hrs)}:00 UTC, TP +%{p['tp_pct']}, ters bölge %{p['adverse_pct']}, "
             f"liq %{p['liq_pct']}, en fazla {p['hold_h']} saat, {p['leverage']:.0f}x, marj {p['margin_usdt']:.0f} USDT, "
             f"ücret %{p['fee_pct']}×2, funding dahil, eklemesiz.")
    L.append("")
    L.append(f"1) HER {p.get('step_h', 24)} SAATTE HER COİNDE AYNI İŞLEM AÇILSAYDI (filtre yok)")
    hdr = f"{'':<10}{'n':>6}{'temiz%':>8}{'TP%':>7}{'liq%':>7}{'-%10%':>7}{'süre%':>7}{'ort.PnL':>9}{'toplam':>9}{'başabaş TP%':>12}"
    L.append(hdr)
    for dname in ("long", "short"):
        b = s["base"][dname]
        L.append(f"{dname:<10}{b['n']:>6}{fmt(b['clean_rate']):>8}{fmt(b['tp_rate']):>7}{fmt(b['liq_rate']):>7}"
                 f"{fmt(b['pain_rate']):>7}{fmt(b['timeout_rate']):>7}{fmt(b['avg_pnl_usdt'], nd=2):>9}"
                 f"{fmt(b['total_pnl_usdt'], nd=0):>9}{fmt(b['breakeven_tp_rate']):>12}")
    L.append("  temiz% = TP'ye ters yönde %10 görmeden ulaşma; -%10% = en az bir kez %10 ters gitme;")
    L.append("  süre% = 96 saatte ne TP ne liq; başabaş TP% = gerçekleşen ort. kazanç/kayıpla sıfır kâr için gereken TP oranı.")
    L.append("")
    L.append("2) COİN BAZINDA (long | short)")
    L.append(f"{'':<10}{'temiz% L':>10}{'liq% L':>8}{'PnL L':>8}{'temiz% S':>10}{'liq% S':>8}{'PnL S':>8}")
    for sym, v in s["per_coin"].items():
        lg, sh = v["long"], v["short"]
        if not lg.get("n"):
            continue
        L.append(f"{sym:<10}{fmt(lg['clean_rate']):>10}{fmt(lg['liq_rate']):>8}{fmt(lg['avg_pnl_usdt'], nd=2):>8}"
                 f"{fmt(sh['clean_rate']):>10}{fmt(sh['liq_rate']):>8}{fmt(sh['avg_pnl_usdt'], nd=2):>8}")
    L.append("")
    L.append(f"3) DOĞRULANMIŞ KOŞULLAR ({len(s['validated'])} / {s['tested']} test; ölçüt: işlem başı PnL farkı, "
             f"%{p['ci_level_pct']} blok-bootstrap aralığı + iki yarıda aynı yön)")
    if not s["validated"]:
        L.append("  YOK. Test edilen hiçbir koşul işlem başı sonucu istatistiksel olarak anlamlı ve dönemin")
        L.append("  iki yarısında tutarlı biçimde değiştirmedi. Brifing bu durumda kanıt iddia etmemeli.")
    for c in sorted(s["validated"], key=lambda c: -abs(c["pnl_lift"])):
        L.append(f"  [{c['direction']}] {c['desc_tr']} ({c['id']}): PnL {c['avg_pnl_true']:+.2f} vs {c['avg_pnl_false']:+.2f} USDT "
                 f"→ {c['pnl_lift']:+.2f} [{c['pnl_ci_low']:+.2f}, {c['pnl_ci_high']:+.2f}], yarılar {c['pnl_half1']:+.2f}/{c['pnl_half2']:+.2f}; "
                 f"temiz %{c['rate_true']:.1f} vs %{c['rate_false']:.1f}, liq %{c['liq_rate_true']:.1f} vs %{c['liq_rate_false']:.1f}, n={c['n_true']}")
    L.append("")
    L.append("4) TÜM KOŞULLAR (doğrulanmamışlar dahil; sadece bilgi, brifingte kanıt olarak kullanılmaz)")
    L.append(f"{'koşul':<20}{'yön':<6}{'n':>5}{'temiz% D/Y':>13}{'liq% D/Y':>11}{'PnL D/Y':>14}{'PnL fark':>9}{'aralık':>16}{'yarılar':>13}{'ok':>3}")
    for c in s["conditions"]:
        if "pnl_lift" not in c:
            L.append(f"{c['id']:<20}{c['direction']:<6}{c['n_true']:>5}   (yetersiz veri)")
            continue
        ci = f"[{fmt(c['pnl_ci_low'], nd=2)},{fmt(c['pnl_ci_high'], nd=2)}]"
        hv = f"{fmt(c['pnl_half1'], nd=2)}/{fmt(c['pnl_half2'], nd=2)}"
        L.append(f"{c['id']:<20}{c['direction']:<6}{c['n_true']:>5}{fmt(c['rate_true']):>7}/{fmt(c['rate_false']):<5}"
                 f"{fmt(c['liq_rate_true']):>6}/{fmt(c['liq_rate_false']):<4}{fmt(c['avg_pnl_true'], nd=2):>7}/{fmt(c['avg_pnl_false'], nd=2):<6}"
                 f"{c['pnl_lift']:>+9.2f}{ci:>16}{hv:>13}{'✔' if c['validated'] else '':>3}")
    L.append("")
    L.append("5) STOP-LOSS KARŞILAŞTIRMASI (aynı işlemler; fark = stop'lu PnL - stop'suz PnL, %95 haftalık bootstrap)")
    L.append(f"   Stop piyasa emriyle, %{p['sl_slippage_pct']} kayma payıyla kapanır. 5x'te fiyat %X stop = %5X ROE kaybı.")

    def sl_table(title, rows):
        L.append(f"  {title}")
        L.append(f"  {'SL':>6}{'TP%':>7}{'SL%':>7}{'liq%':>7}{'ort.PnL':>9}{'toplam':>9}{'en kötü':>9}{'fark':>8}{'aralık':>18}{'yarılar':>15}")
        for r in rows:
            name = "yok" if r["sl_pct"] is None else f"%{r['sl_pct']:g}"
            extra = ""
            if r["sl_pct"] is not None:
                extra = (f"{r['diff_vs_none']:>+8.2f}{'[' + format(r['ci_low'], '+.2f') + ',' + format(r['ci_high'], '+.2f') + ']':>18}"
                         f"{format(r['half1'], '+.2f') + '/' + format(r['half2'], '+.2f'):>15}{' ✔' if r['significant'] else ''}")
            L.append(f"  {name:>6}{r['tp_rate']:>7.1f}{r['sl_rate']:>7.1f}{r['liq_rate']:>7.1f}{r['avg_pnl_usdt']:>9.2f}"
                     f"{r['total_pnl_usdt']:>9.0f}{r['worst_trade_usdt']:>9.2f}{extra}")

    for dname in ("long", "short"):
        sl_table(f"[{dname}] tüm işlemler", s["sl_analysis"]["base"][dname])
    for key, rows in s["sl_analysis"]["validated"].items():
        cid, dname = key.split("|")
        sl_table(f"[{dname}] sadece '{cid}' doğruyken", rows)
    L.append("  ✔ = stop'suza göre fark %95 aralıkta sıfırdan farklı ve iki yarıda aynı yönde.")
    L.append("  Not: sıkı stoplarda (%2-3) aynı mumda TP ve stop sık görülür; stop önce sayıldığı için sonuç kötümserdir.")
    L.append("")
    L.append("NOTLAR")
    L.append("- Mum içi sıra bilinmediği için aynı saatte TP ve ters seviye birlikte görülürse ters seviye sayıldı (kötümser).")
    L.append("- Sonuçlar bu dönemin piyasa rejimine bağlıdır; geçmiş başarı geleceği garanti etmez.")
    L.append("- 11 coin aynı gün büyük ölçüde birlikte hareket eder; etkin örneklem işlem sayısından küçüktür (bootstrap bunu hafta bazında hesaba katar).")
    L.append("- Liq'e yakın ekleme simüle edilmedi; ekleme, liq olan işlemlerde kaybı ~2 katına çıkarır.")
    L.append("- PnL'i nadir ama büyük liq kayıpları (-50 USDT) belirler; birkaç liq farkı sonucu değiştirebilir, bu yüzden eşik sıkıdır.")
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())
