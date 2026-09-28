"""Brifing (canlı) ve backtest'in ORTAK hesapları.

Aynı fonksiyonlar hem binance_collector.py (her saat, canlı API verisi) hem de
backtest.py (geçmiş veri) tarafından çağrılır. Böylece brifingte "aktif" görünen
bir koşul, backtest'te test edilen koşulla birebir aynı tanıma sahip olur.

Zaman kuralı: T bir saat başıdır (UTC, ms). Özellikler sadece T anında
bilinebilecek veriden hesaplanır (T'den önce KAPANMIŞ mumlar, zaman damgası
T'ye eşit veya önce olan ölçümler). Geleceğe bakma (lookahead) yoktur.

Bar biçimi: (open_time_ms, open, high, low, close, quote_volume, taker_buy_quote)
"""
from bisect import bisect_right

HOUR = 3_600_000
DAY = 24 * HOUR
T_, O_, H_, L_, C_, QV_, TBQ_ = range(7)

# 5x isolated long liq ≈ giriş × (1 − 1/5 + MMR); MMR küçük pozisyonda ~%0,4–1.
LIQ_DISTANCE_PCT = 19.5
# Pencere uzunlukları: canlı API limit=N+1 ister (son mum henüz kapanmamıştır),
# backtest aynı N kapanmış mumu kullanır. EMA'lar pencereye duyarlı olduğu için ikisi eşit olmalı.
N_1H = 999
N_1D = 259


def pct(new, old):
    if new is None or not old:
        return None
    return (new - old) / old * 100


def ema(values, n):
    """Standart EMA (ilk n değerin ortalamasıyla başlar). Yetersiz veri → None."""
    if len(values) < n:
        return None
    k = 2 / (n + 1)
    e = sum(values[:n]) / n
    for v in values[n:]:
        e = v * k + e * (1 - k)
    return e


def atr(bars, n=14):
    """Wilder ATR. Yetersiz veri → None."""
    if len(bars) < n + 1:
        return None
    trs = [
        max(b[H_] - b[L_], abs(b[H_] - p[C_]), abs(b[L_] - p[C_]))
        for p, b in zip(bars, bars[1:])
    ]
    a = sum(trs[:n]) / n
    for tr in trs[n:]:
        a = (a * (n - 1) + tr) / n
    return a


def pctl_rank(hist, v, min_len=20):
    """v'nin geçmiş içindeki yüzdelik sırası (0-100, geçmişin yüzde kaçı ≤ v)."""
    hist = [x for x in hist if x is not None]
    if v is None or len(hist) < min_len:
        return None
    return 100 * sum(1 for x in hist if x <= v) / len(hist)


def resample(bars, hours):
    """Saatlik barları UTC hizalı `hours` saatlik barlara çevirir; eksik grup atılır."""
    span = hours * HOUR
    out, key, cnt, g = [], None, 0, None
    for b in bars:
        k = b[T_] // span * span
        if k != key:
            if g is not None and cnt == hours:
                out.append(tuple(g))
            key, cnt = k, 0
            g = [k, b[O_], b[H_], b[L_], b[C_], 0.0, 0.0]
        g[H_] = max(g[H_], b[H_])
        g[L_] = min(g[L_], b[L_])
        g[C_] = b[C_]
        g[QV_] += b[QV_]
        g[TBQ_] += b[TBQ_]
        cnt += 1
    if g is not None and cnt == hours:
        out.append(tuple(g))
    return out


class Series:
    """Zaman damgalı ölçüm serisi; at(t) = zaman damgası ≤ t olan son değer."""

    def __init__(self, pairs):
        pairs = sorted((int(t), v) for t, v in pairs if v is not None)
        self.t = [p[0] for p in pairs]
        self.v = [p[1] for p in pairs]

    def __len__(self):
        return len(self.t)

    def at(self, t, max_age=2 * HOUR):
        i = bisect_right(self.t, t) - 1
        if i < 0 or t - self.t[i] > max_age:
            return None
        return self.v[i]

    def between(self, t0, t1):
        """t0 < ts ≤ t1 aralığındaki değerler."""
        return self.v[bisect_right(self.t, t0):bisect_right(self.t, t1)]


def funding_to_8h(records):
    """[(t, rate, interval_h|None)] → Series(t, 8 saate normalize funding, %).

    Bazı coinlerde funding 4 saatte bir ödenir; farklı aralıkları karşılaştırmak
    için oran 8 saatlik eşdeğere çevrilir. Aralık verilmemişse ardışık iki
    ödeme arasındaki süreden bulunur.
    """
    recs = sorted(records)
    out = []
    for i, (t, rate, iv) in enumerate(recs):
        if not iv:
            if i > 0:
                iv = (t - recs[i - 1][0]) / HOUR
            elif len(recs) > 1:
                iv = (recs[1][0] - t) / HOUR
            else:
                iv = 8
        iv = min((1, 2, 4, 8), key=lambda x: abs(x - iv))
        out.append((t, rate * 100 * 8 / iv))
    return Series(out)


def funding_interval_h(records):
    recs = sorted(records)
    if len(recs) >= 2:
        iv = (recs[-1][0] - recs[-2][0]) / HOUR
        return min((1, 2, 4, 8), key=lambda x: abs(x - iv))
    return None


def compute_features(fut, daily, T, spot=None, oi=None, longp=None, top=None, funding=None):
    """T anındaki özellikler.

    fut:   T'den önce kapanmış saatlik futures barları (en az 169; canlı ve backtest son N_1H)
    daily: T'den önce kapanmış günlük barlar (canlı ve backtest son N_1D)
    spot:  T'den önce kapanmış saatlik spot barları (opsiyonel)
    oi, longp, top: Series (OI USDT, global long hesap %, top trader pozisyon oranı)
    funding: funding_to_8h() çıktısı
    """
    if len(fut) < 169:
        return None
    f = {}
    price = fut[-1][C_]
    last24 = fut[-24:]
    hi, lo = max(b[H_] for b in last24), min(b[L_] for b in last24)
    f["price"] = price
    f["ret_24h"] = pct(price, fut[-25][C_])
    f["ret_7d"] = pct(price, fut[-169][C_])
    f["high_24h_calc"], f["low_24h_calc"] = hi, lo
    f["range_24h"] = pct(hi, lo)
    f["pos_24h"] = (price - lo) / (hi - lo) if hi > lo else None

    closes = [b[C_] for b in daily]
    for n in (20, 50, 200):
        e = ema(closes, n)
        f[f"ema{n}_1d"] = e
        f[f"dist_ema{n}_1d"] = pct(price, e)
    a = atr(daily)
    f["atr_pct_1d"] = a / price * 100 if a else None
    f["liq_in_atr"] = LIQ_DISTANCE_PCT / f["atr_pct_1d"] if f["atr_pct_1d"] else None
    f["tp2_in_atr"] = 2 / f["atr_pct_1d"] if f["atr_pct_1d"] else None
    if daily:
        f["prev_day_high"], f["prev_day_low"] = daily[-1][H_], daily[-1][L_]
        f["high_7d"] = max(b[H_] for b in daily[-7:])
        f["low_7d"] = min(b[L_] for b in daily[-7:])

    c4 = [b[C_] for b in resample(fut, 4)]
    f["ema20_4h"], f["ema50_4h"] = ema(c4, 20), ema(c4, 50)

    qv = sum(b[QV_] for b in last24)
    tbq = sum(b[TBQ_] for b in last24)
    f["perp_taker_ratio_24h"] = tbq / (qv - tbq) if qv > tbq else None
    f["perp_imb_24h"] = (2 * tbq - qv) / qv if qv else None
    if spot and len(spot) >= 24 and spot[-1][T_] == fut[-1][T_]:
        s24 = spot[-24:]
        sqv = sum(b[QV_] for b in s24)
        stbq = sum(b[TBQ_] for b in s24)
        f["spot_imb_24h"] = (2 * stbq - sqv) / sqv if sqv else None
        f["spot_perp_vol_ratio"] = sqv / qv if qv else None

    if oi is not None:
        now = oi.at(T)
        f["oi_usdt_calc"] = now
        f["oi_chg_24h"] = pct(now, oi.at(T - DAY))
        f["oi_chg_7d"] = pct(now, oi.at(T - 7 * DAY))

    # Long/short oranları 4 saatlik noktalarda örneklenir (canlı API'deki 4h seri ile aynı)
    base4 = T // (4 * HOUR) * (4 * HOUR)
    if longp is not None:
        f["long_pct"] = longp.at(base4, 4 * HOUR)
        hist = [longp.at(base4 - k * 4 * HOUR, 4 * HOUR) for k in range(180)]
        f["long_pct_pctl_30d"] = pctl_rank(hist, f["long_pct"])
    if top is not None:
        f["top_ratio"] = top.at(base4, 4 * HOUR)
        hist = [top.at(base4 - k * 4 * HOUR, 4 * HOUR) for k in range(180)]
        f["top_ratio_pctl_30d"] = pctl_rank(hist, f["top_ratio"])

    if funding is not None:
        f["funding_8h"] = funding.at(T, 9 * HOUR)
        f["funding_pctl_30d"] = pctl_rank(funding.between(T - 30 * DAY, T), f["funding_8h"])
        w = funding.between(T - 7 * DAY, T)
        f["funding_avg_7d_8h"] = sum(w) / len(w) if w else None
    return f


def _cond(fn, *keys):
    def check(f):
        if f is None or any(f.get(k) is None for k in keys):
            return None
        return bool(fn(f))
    return check


# (id, Türkçe açıklama, fonksiyon). Backtest her birini long ve short için ayrı test eder.
CONDITIONS = [
    ("trend_up_1d", "fiyat günlük EMA50 üstünde", _cond(lambda f: f["price"] > f["ema50_1d"], "ema50_1d")),
    ("above_ema200_1d", "fiyat günlük EMA200 üstünde", _cond(lambda f: f["price"] > f["ema200_1d"], "ema200_1d")),
    ("trend_up_4h", "4 saatlikte EMA20 > EMA50", _cond(lambda f: f["ema20_4h"] > f["ema50_4h"], "ema20_4h", "ema50_4h")),
    ("ret7d_pos", "son 7 gün getirisi pozitif", _cond(lambda f: f["ret_7d"] > 0, "ret_7d")),
    ("drop_5pct_24h", "24 saatte -%5 veya daha fazla düşüş", _cond(lambda f: f["ret_24h"] <= -5, "ret_24h")),
    ("pump_5pct_24h", "24 saatte +%5 veya daha fazla yükseliş", _cond(lambda f: f["ret_24h"] >= 5, "ret_24h")),
    ("wide_range_24h", "24 saatlik aralık ≥ %10", _cond(lambda f: f["range_24h"] >= 10, "range_24h")),
    ("near_day_low", "fiyat 24 saatlik aralığın alt çeyreğinde", _cond(lambda f: f["pos_24h"] <= 0.25, "pos_24h")),
    ("near_day_high", "fiyat 24 saatlik aralığın üst çeyreğinde", _cond(lambda f: f["pos_24h"] >= 0.75, "pos_24h")),
    ("high_vol", "günlük ATR ≥ %5 (yüksek oynaklık)", _cond(lambda f: f["atr_pct_1d"] >= 5, "atr_pct_1d")),
    ("funding_high", "funding kendi 30 gününün en yüksek %10'unda", _cond(lambda f: f["funding_pctl_30d"] >= 90, "funding_pctl_30d")),
    ("funding_low", "funding kendi 30 gününün en düşük %10'unda", _cond(lambda f: f["funding_pctl_30d"] <= 10, "funding_pctl_30d")),
    ("funding_negative", "funding negatif (short'lar ödüyor)", _cond(lambda f: f["funding_8h"] < 0, "funding_8h")),
    ("oi_up_10", "açık pozisyon 24 saatte ≥ +%10", _cond(lambda f: f["oi_chg_24h"] >= 10, "oi_chg_24h")),
    ("oi_down_10", "açık pozisyon 24 saatte ≤ -%10", _cond(lambda f: f["oi_chg_24h"] <= -10, "oi_chg_24h")),
    ("long_crowd_70", "long hesap oranı ≥ %70", _cond(lambda f: f["long_pct"] >= 70, "long_pct")),
    ("long_pctl_high", "long hesap oranı kendi 30 gününün en yüksek %10'unda", _cond(lambda f: f["long_pct_pctl_30d"] >= 90, "long_pct_pctl_30d")),
    ("long_pctl_low", "long hesap oranı kendi 30 gününün en düşük %10'unda", _cond(lambda f: f["long_pct_pctl_30d"] <= 10, "long_pct_pctl_30d")),
    ("top_pctl_high", "büyük hesapların long pozisyonu 30 günün en yüksek %10'unda", _cond(lambda f: f["top_ratio_pctl_30d"] >= 90, "top_ratio_pctl_30d")),
    ("top_pctl_low", "büyük hesapların long pozisyonu 30 günün en düşük %10'unda", _cond(lambda f: f["top_ratio_pctl_30d"] <= 10, "top_ratio_pctl_30d")),
    ("perp_sellers", "vadelide 24 saat agresif satıcı baskın (taker oranı < 0,95)", _cond(lambda f: f["perp_taker_ratio_24h"] < 0.95, "perp_taker_ratio_24h")),
    ("perp_buyers", "vadelide 24 saat agresif alıcı baskın (taker oranı > 1,05)", _cond(lambda f: f["perp_taker_ratio_24h"] > 1.05, "perp_taker_ratio_24h")),
    ("spot_leads", "spotta alım baskısı vadeliden güçlü", _cond(lambda f: f["spot_imb_24h"] > f["perp_imb_24h"], "spot_imb_24h", "perp_imb_24h")),
    ("shorts_building", "fiyat düşerken açık pozisyon ≥ +%5 (short birikimi olası)", _cond(lambda f: f["ret_24h"] < 0 and f["oi_chg_24h"] >= 5, "ret_24h", "oi_chg_24h")),
    ("crowded_long_rally", "fiyat ve açık pozisyon artarken funding 30 günlük %80 üstü", _cond(lambda f: f["ret_24h"] > 0 and f["oi_chg_24h"] >= 5 and f["funding_pctl_30d"] >= 80, "ret_24h", "oi_chg_24h", "funding_pctl_30d")),
    ("long_flush", "fiyat ≤ -%3 ve açık pozisyon ≤ -%5 (long tasfiyesi olası)", _cond(lambda f: f["ret_24h"] <= -3 and f["oi_chg_24h"] <= -5, "ret_24h", "oi_chg_24h")),
    ("btc_trend_up", "BTC günlük EMA50 üstünde", _cond(lambda f: f["btc_trend_up"], "btc_trend_up")),
    ("filter_green", "brifingteki 🟢 filtresi", _cond(lambda f: f["range_24h"] <= 5 and f["long_pct"] < 70 and abs(f["oi_chg_24h"]) < 10, "range_24h", "long_pct", "oi_chg_24h")),
    ("filter_red", "brifingteki 🔴 filtresi", _cond(lambda f: f["range_24h"] >= 10 or abs(f["oi_chg_24h"]) >= 15 or f["ret_24h"] <= -5, "range_24h", "oi_chg_24h", "ret_24h")),
]
CONDITION_DESC = {cid: desc for cid, desc, _ in CONDITIONS}


def evaluate_conditions(f):
    return {cid: fn(f) for cid, _, fn in CONDITIONS}
