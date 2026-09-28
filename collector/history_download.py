#!/usr/bin/env python3
"""Backtest için geçmiş veri indirir (VPS'te çalışır; API anahtarı gerekmez).

Kaynaklar:
  - Futures 1h mum:   /fapi/v1/klines           (canlı toplayıcıyla aynı uç)
  - Spot 1h mum:      /api/v3/klines
  - Funding geçmişi:  /fapi/v1/fundingRate
  - OI + long/short:  data.binance.vision günlük "metrics" arşivi
                      (API bu verileri sadece son 30 gün için veriyor)

Çıktı: data/history/<SYMBOL>/{fut_1h,spot_1h,funding,metrics}.csv
Tekrar çalıştırılırsa sadece eksik kısmı indirir.

Ortam değişkenleri: SYMBOLS, DAYS (varsayılan 365), HIST_DIR
"""
import csv
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from binance_collector import DEFAULT_SYMBOLS  # noqa: E402

FAPI = "https://fapi.binance.com"
SPOT = "https://api.binance.com"
ARCHIVE = "https://data.binance.vision/data/futures/um/daily/metrics"
HOUR = 3_600_000
DAY = 24 * HOUR
DAYS = int(os.getenv("DAYS", "365"))
WARMUP_DAYS = 270   # EMA200 (260 günlük pencere) + tampon
METRIC_WARMUP = 32  # 30 günlük yüzdelik için
HIST_DIR = Path(os.getenv("HIST_DIR", HERE / "data" / "history"))


def http(url, retries=4):
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (418, 429):  # rate limit: bekle
                time.sleep(int(e.headers.get("Retry-After", "30")))
                last = e
                continue
            if 400 <= e.code < 500:
                raise RuntimeError(f"HTTP {e.code} {url}: {e.read().decode()[:200]}")
            last = e
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
        time.sleep(2 ** attempt)
    raise RuntimeError(f"başarısız: {url}: {last}")


def read_csv(path):
    if not path.exists():
        return []
    with open(path) as f:
        return list(csv.reader(f))[1:]


def write_csv(path, header, rows):
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    tmp.replace(path)


def fetch_klines(base, path, symbol, start_ms, end_ms, out):
    """Mumları sayfalayarak indirir, mevcut dosyaya ekler (sadece kapanmış mumlar)."""
    header = ["open_time", "open", "high", "low", "close", "quote_volume", "taker_buy_quote"]
    rows = {int(x[0]): x for x in read_csv(out)}
    t = max(rows) + HOUR if rows else start_ms
    n0 = len(rows)
    while t + HOUR <= end_ms:
        q = urllib.parse.urlencode({"symbol": symbol, "interval": "1h", "startTime": t, "limit": 1000})
        data = json.loads(http(f"{base}{path}?{q}") or b"[]")
        if not data:
            break
        for k in data:
            ot = int(k[0])
            if ot + HOUR <= end_ms:
                rows[ot] = [ot, k[1], k[2], k[3], k[4], k[7], k[10]]
        nt = int(data[-1][0]) + HOUR
        if nt <= t:
            break
        t = nt
        time.sleep(0.25)  # ağırlık limiti: 1000'lik istek = 5 ağırlık, dakikada 2400
    write_csv(out, header, [rows[k] for k in sorted(rows)])
    return len(rows) - n0, len(rows)


def fetch_funding(symbol, start_ms, end_ms, out):
    rows = {int(x[0]): x for x in read_csv(out)}
    t = max(rows) + 1 if rows else start_ms
    n0 = len(rows)
    while t < end_ms:
        q = urllib.parse.urlencode({"symbol": symbol, "startTime": t, "limit": 1000})
        data = json.loads(http(f"{FAPI}/fapi/v1/fundingRate?{q}") or b"[]")
        if not data:
            break
        for x in data:
            rows[int(x["fundingTime"])] = [int(x["fundingTime"]), x["fundingRate"]]
        nt = int(data[-1]["fundingTime"]) + 1
        if nt <= t or len(data) < 1000:
            break
        t = nt
        time.sleep(0.5)  # fundingRate: 5 dakikada 500 istek
    write_csv(out, ["funding_time", "funding_rate"], [rows[k] for k in sorted(rows)])
    return len(rows) - n0, len(rows)


def parse_time(s):
    s = s.strip()
    if s.isdigit():
        v = int(s)
        return v // 1000 if v > 10**14 else v  # mikro saniye → ms
    dt = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


METRIC_COLS = ["create_time", "sum_open_interest_value", "count_long_short_ratio",
               "sum_toptrader_long_short_ratio"]


def parse_metrics_zip(blob):
    """Metrics zip → [(t_ms, oi_usdt, long_pct, top_pos_ratio)]"""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        text = z.read(name).decode()
    rd = csv.reader(io.StringIO(text))
    header = [h.strip() for h in next(rd)]
    missing = [c for c in METRIC_COLS if c not in header]
    if missing:
        raise RuntimeError(f"metrics başlığı beklenenden farklı: {header} (eksik: {missing})")
    ix = {c: header.index(c) for c in METRIC_COLS}
    out = []
    for row in rd:
        if not row:
            continue
        try:
            r = float(row[ix["count_long_short_ratio"]])
            out.append((
                parse_time(row[ix["create_time"]]),
                float(row[ix["sum_open_interest_value"]]),
                r / (1 + r) * 100,
                float(row[ix["sum_toptrader_long_short_ratio"]]),
            ))
        except (ValueError, IndexError):
            continue  # boş/bozuk satır
    return out


def fetch_metrics(symbol, days, raw_dir, out):
    """Günlük metrics zip'lerini indirir (paralel), saatlik son değere indirger."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    missing_file = raw_dir / "missing.txt"
    known_missing = set(missing_file.read_text().split()) if missing_file.exists() else set()
    today = datetime.now(timezone.utc).date()
    dates = [(today - timedelta(days=i)).isoformat() for i in range(1, days + 1)]
    todo = [d for d in dates if not (raw_dir / f"{d}.zip").exists() and d not in known_missing]

    def dl(d):
        blob = http(f"{ARCHIVE}/{symbol}/{symbol}-metrics-{d}.zip")
        if blob is None:
            return d, False
        (raw_dir / f"{d}.zip").write_bytes(blob)
        return d, True

    got, miss = 0, []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for d, ok in ex.map(dl, todo):
            if ok:
                got += 1
            else:
                miss.append(d)
    # 3 günden eski olup yine de olmayan günleri tekrar deneme
    old = [d for d in miss if d < (today - timedelta(days=3)).isoformat()]
    if old:
        missing_file.write_text("\n".join(sorted(known_missing | set(old))))

    hourly = {}
    bad = 0
    for p in sorted(raw_dir.glob("*.zip")):
        try:
            for t, oi, lp, top in parse_metrics_zip(p.read_bytes()):
                hourly[t // HOUR] = max(hourly.get(t // HOUR, (0,)), (t, oi, lp, top))
        except zipfile.BadZipFile:
            p.unlink()  # bozuk indirme: bir sonraki çalıştırmada tekrar iner
            bad += 1
    rows = [[t, round(oi, 2), round(lp, 3), top] for t, oi, lp, top in
            (hourly[k] for k in sorted(hourly))]
    write_csv(out, ["t", "oi_usdt", "long_pct", "top_pos_ratio"], rows)
    return got, len(miss), bad, len(rows)


def main():
    symbols = [s.strip().upper() for s in os.getenv("SYMBOLS", "").split(",") if s.strip()] \
        or DEFAULT_SYMBOLS
    now_ms = int(time.time() * 1000) // HOUR * HOUR
    k_start = now_ms - (DAYS + WARMUP_DAYS) * DAY
    f_start = now_ms - (DAYS + METRIC_WARMUP) * DAY
    print(f"Geçmiş veri: {len(symbols)} coin, {DAYS} gün (+ısınma) → {HIST_DIR}")
    failed = []
    for sym in symbols:
        d = HIST_DIR / sym
        d.mkdir(parents=True, exist_ok=True)
        try:
            a = fetch_klines(FAPI, "/fapi/v1/klines", sym, k_start, now_ms, d / "fut_1h.csv")
            try:
                b = fetch_klines(SPOT, "/api/v3/klines", sym, k_start, now_ms, d / "spot_1h.csv")
            except Exception as e:  # spot opsiyonel: spot_leads koşulu test edilemez, gerisi etkilenmez
                b = ("HATA", 0)
                print(f"{sym:<9} spot alınamadı: {e}", file=sys.stderr)
            c = fetch_funding(sym, f_start, now_ms, d / "funding.csv")
            m = fetch_metrics(sym, DAYS + METRIC_WARMUP, d / "metrics_raw", d / "metrics.csv")
            print(f"{sym:<9} futures +{a[0]} (={a[1]}) | spot +{b[0]} (={b[1]}) | "
                  f"funding +{c[0]} (={c[1]}) | metrics: yeni gün {m[0]}, bulunamayan {m[1]}, "
                  f"bozuk {m[2]}, saatlik satır {m[3]}")
        except Exception as e:
            failed.append(sym)
            print(f"{sym:<9} HATA: {e}", file=sys.stderr)
    if failed:
        print(f"Başarısız: {', '.join(failed)}", file=sys.stderr)
    return 1 if len(failed) == len(symbols) else 0


if __name__ == "__main__":
    sys.exit(main())
