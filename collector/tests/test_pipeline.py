"""Toplayıcı, özellik hesapları ve backtest testleri (sadece stdlib).

Çalıştırma: python3 -m unittest discover -s collector/tests -v
"""
import csv
import io
import json
import math
import random
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import features as fx  # noqa: E402

HOUR, DAY = fx.HOUR, fx.DAY
T0 = 1_700_006_400_000 // DAY * DAY  # UTC gün başı


def bar(t, o, h, l, c, qv=100.0, tbq=50.0):
    return (t, o, h, l, c, qv, tbq)


class TestIndicators(unittest.TestCase):
    def test_ema(self):
        self.assertIsNone(fx.ema([1, 2], 3))
        self.assertAlmostEqual(fx.ema([1, 2, 3], 3), 2.0)
        # 4. değer: 4*0.5 + 2*0.5 = 3
        self.assertAlmostEqual(fx.ema([1, 2, 3, 4], 3), 3.0)

    def test_atr_constant_range(self):
        bars = [bar(i * DAY, 10, 11, 9, 10) for i in range(30)]
        self.assertAlmostEqual(fx.atr(bars), 2.0)

    def test_pctl_rank(self):
        self.assertIsNone(fx.pctl_rank([1] * 5, 1))
        self.assertEqual(fx.pctl_rank(list(range(1, 101)), 90), 90)

    def test_resample_drops_incomplete(self):
        bars = [bar(T0 + i * HOUR, i, i + 1, i - 1, i + 0.5) for i in range(10)]
        out = fx.resample(bars, 4)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0][1], 0)       # open ilk barın
        self.assertEqual(out[0][4], 3.5)     # close son barın
        self.assertEqual(out[0][2], 4)       # high max
        self.assertEqual(out[0][5], 400.0)   # hacim toplam

    def test_series_at(self):
        s = fx.Series([(T0, 1.0), (T0 + HOUR, 2.0)])
        self.assertEqual(s.at(T0 + HOUR), 2.0)
        self.assertEqual(s.at(T0 + HOUR - 1), 1.0)
        self.assertIsNone(s.at(T0 - 1))
        self.assertIsNone(s.at(T0 + 10 * HOUR))  # çok eski
        self.assertEqual(s.between(T0, T0 + HOUR), [2.0])

    def test_funding_normalized_to_8h(self):
        recs = [(T0 + i * 4 * HOUR, 0.0001, None) for i in range(10)]
        s = fx.funding_to_8h(recs)
        self.assertAlmostEqual(s.v[-1], 0.02)  # 4 saatlik %0,01 = 8 saatlik %0,02
        self.assertEqual(fx.funding_interval_h(recs), 4)


def make_history(n_days, seed, plant=False):
    """Sentetik saatlik futures/spot mumları, funding (8s) ve metrics.

    plant=True: 00:00 funding'i negatif olan günlerde 06:00-30:00 arası
    yukarı sürüklenme eklenir (backtest'in yakalaması gereken gerçek etki).
    """
    rng = random.Random(seed)
    n = n_days * 24
    funding = []
    drift = [0.0] * (n + 48)
    for dday in range(n_days):
        for k in range(3):
            t = T0 + dday * DAY + k * 8 * HOUR
            rate = rng.gauss(0.00005, 0.0001)
            funding.append((t, rate))
            if plant and k == 0 and rate < 0:
                for h in range(6, 30):
                    drift[dday * 24 + h] += 0.0012
    fut, spot, met = [], [], []
    p, oi, lp = 100.0, 1e9, 60.0
    for i in range(n):
        t = T0 + i * HOUR
        o = p
        p = o * math.exp(rng.gauss(drift[i], 0.006))
        h = max(o, p) * (1 + abs(rng.gauss(0, 0.002)))
        l = min(o, p) * (1 - abs(rng.gauss(0, 0.002)))
        qv = rng.uniform(5e6, 1e7)
        fut.append((t, o, h, l, p, qv, qv * rng.uniform(0.45, 0.55)))
        spot.append((t, o, h, l, p, qv / 3, qv / 3 * rng.uniform(0.45, 0.55)))
        oi *= math.exp(rng.gauss(0, 0.01))
        lp = min(80, max(40, lp + rng.gauss(0, 0.5)))
        met.append((t + HOUR - 5 * 60_000, oi, lp, rng.uniform(0.8, 2.5)))
    return fut, spot, funding, met


def write_history(root, sym, hist):
    fut, spot, funding, met = hist
    d = Path(root) / sym
    d.mkdir(parents=True)
    for name, rows, hdr in (
        ("fut_1h.csv", fut, ["open_time", "open", "high", "low", "close", "quote_volume", "taker_buy_quote"]),
        ("spot_1h.csv", spot, ["open_time", "open", "high", "low", "close", "quote_volume", "taker_buy_quote"]),
        ("funding.csv", funding, ["funding_time", "funding_rate"]),
        ("metrics.csv", met, ["t", "oi_usdt", "long_pct", "top_pos_ratio"]),
    ):
        with open(d / name, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(hdr)
            w.writerows(rows)


class TestSimulate(unittest.TestCase):
    def setUp(self):
        import backtest
        self.bt = backtest

    def sym(self, bars):
        return {"fut": bars, "fund_raw_t": [], "fund_raw": []}

    def flat(self, n, extra):
        bars = [bar(T0 + i * HOUR, 100, 100.5, 99.5, 100) for i in range(n)]
        for i, b in extra.items():
            bars[i] = b
        return bars

    def test_clean_tp_long(self):
        bars = self.flat(100, {3: bar(T0 + 3 * HOUR, 100, 102.5, 99.5, 102)})
        out = self.bt.simulate(self.sym(bars), 0, 1)
        self.assertEqual(out["res"], "tp")
        self.assertTrue(out["clean"])
        self.assertAlmostEqual(out["pnl"], 250 * 0.02 - 2 * 250 * 0.0005)
        self.assertEqual(out["hours"], 4)

    def test_same_bar_tp_and_adverse_is_not_clean(self):
        bars = self.flat(100, {2: bar(T0 + 2 * HOUR, 100, 103, 89, 101)})
        out = self.bt.simulate(self.sym(bars), 0, 1)
        self.assertEqual(out["res"], "tp")
        self.assertFalse(out["clean"])
        self.assertTrue(out["pain"])

    def test_liq_before_tp_in_same_bar(self):
        bars = self.flat(100, {2: bar(T0 + 2 * HOUR, 100, 103, 80, 101)})
        out = self.bt.simulate(self.sym(bars), 0, 1)
        self.assertEqual(out["res"], "liq")
        self.assertEqual(out["pnl"], -50)

    def test_short_tp_and_timeout(self):
        bars = self.flat(100, {5: bar(T0 + 5 * HOUR, 100, 100.2, 97.9, 98)})
        self.assertEqual(self.bt.simulate(self.sym(bars), 0, -1)["res"], "tp")
        out = self.bt.simulate(self.sym(self.flat(100, {})), 0, -1)
        self.assertEqual(out["res"], "timeout")
        self.assertAlmostEqual(out["pnl"], -0.25)  # sadece ücret

    def test_window_too_short(self):
        self.assertIsNone(self.bt.simulate(self.sym(self.flat(50, {})), 0, 1))

    def test_funding_cost_long(self):
        bars = self.flat(100, {})
        s = {"fut": bars, "fund_raw_t": [T0 + 8 * HOUR], "fund_raw": [(T0 + 8 * HOUR, 0.001)]}
        out = self.bt.simulate(s, 0, 1)
        self.assertAlmostEqual(out["pnl"], -0.25 - 250 * 0.001)


class TestMetricsParsing(unittest.TestCase):
    def test_parse_zip_and_times(self):
        import history_download as hd
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("BTCUSDT-metrics-2024-01-01.csv",
                       "create_time,symbol,sum_open_interest,sum_open_interest_value,"
                       "count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,"
                       "count_long_short_ratio,sum_taker_long_short_vol_ratio\n"
                       "2024-01-01 00:05:00,BTCUSDT,100,4000000,1.5,1.2,3.0,0.9\n"
                       ",,,,,,,\n")
        rows = hd.parse_metrics_zip(buf.getvalue())
        self.assertEqual(len(rows), 1)
        t, oi, lp, top = rows[0]
        self.assertEqual(t, 1704067500000)
        self.assertEqual(oi, 4000000)
        self.assertAlmostEqual(lp, 75.0)  # 3/(1+3)
        self.assertEqual(top, 1.2)
        self.assertEqual(hd.parse_time("1735689600000000"), 1735689600000)

    def test_wrong_header_is_loud(self):
        import history_download as hd
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("x.csv", "a,b\n1,2\n")
        with self.assertRaises(RuntimeError):
            hd.parse_metrics_zip(buf.getvalue())


def run_backtest(tmp, hists, boot=300):
    import backtest as bt
    hist_dir = Path(tmp) / "history"
    for sym, h in hists.items():
        write_history(hist_dir, sym, h)
    with mock.patch.object(bt, "HIST_DIR", hist_dir), \
            mock.patch.object(bt, "DATA_DIR", Path(tmp)), \
            mock.patch.dict(bt.P, {"bootstrap": boot, "days": 330}), \
            mock.patch.dict("os.environ", {"SYMBOLS": ",".join(hists)}), \
            mock.patch("builtins.print"):
        bt._btc_cache.clear()
        rc = bt.main()
    assert rc == 0
    return json.loads((Path(tmp) / "backtest_summary.json").read_text())


class TestBacktestEndToEnd(unittest.TestCase):
    def test_detects_planted_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = run_backtest(tmp, {"BTCUSDT": make_history(400, 1, plant=True),
                                   "ETHUSDT": make_history(400, 2, plant=True)})
            ids = {(c["id"], c["direction"]) for c in s["validated"]}
            self.assertIn(("funding_negative", "long"), ids)
            c = next(c for c in s["conditions"] if c["id"] == "funding_negative" and c["direction"] == "long")
            self.assertGreater(c["lift_pp"], 10)
            self.assertGreater(s["base"]["long"]["n"], 500)
            self.assertTrue((Path(tmp) / "backtest_report.txt").read_text().startswith("BACKTEST RAPORU"))

    def test_noise_produces_no_false_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = run_backtest(tmp, {"BTCUSDT": make_history(400, 3), "ETHUSDT": make_history(400, 4)})
            self.assertLessEqual(len(s["validated"]), 1, [c["id"] for c in s["validated"]])
            self.assertGreater(s["tested"], 40)


class TestCollector(unittest.TestCase):
    """Canlı toplayıcıyı sahte API cevaplarıyla uçtan uca çalıştırır."""

    def fake_api(self, hist, T):
        fut, spot, funding, met = hist
        fut = [b for b in fut if b[0] < T + HOUR]  # son (oluşan) mum dahil
        daily = fx.resample(fut, 24)

        def kl(bars):
            return [[b[0], str(b[1]), str(b[2]), str(b[3]), str(b[4]), "0", b[0] + HOUR - 1,
                     str(b[5]), 1, "0", str(b[6]), "0"] for b in bars]

        def get(path, params=None, base=None):
            p = params or {}
            if path == "/fapi/v1/premiumIndex":
                return [{"symbol": "BTCUSDT", "markPrice": str(fut[-1][4]), "lastFundingRate": "0.0001",
                         "nextFundingTime": T + 3 * HOUR}]
            if path == "/fapi/v1/ticker/24hr":
                return [{"symbol": "BTCUSDT", "lastPrice": str(fut[-1][4]), "priceChangePercent": "1.5",
                         "highPrice": "110", "lowPrice": "100", "quoteVolume": "1e9"}]
            if path == "/fapi/v1/klines":
                return kl(fut[-p["limit"]:] if p["interval"] == "1h" else daily[-p["limit"]:])
            if path == "/api/v3/klines":
                return kl(spot[:len(fut)][-p["limit"]:])
            if path == "/fapi/v1/fundingRate":
                return [{"fundingTime": t, "fundingRate": str(r)} for t, r in funding
                        if p["startTime"] <= t <= T]
            m = [x for x in met if x[0] <= T]
            if path == "/futures/data/openInterestHist":
                return [{"timestamp": (x[0] // HOUR + 1) * HOUR, "sumOpenInterestValue": str(x[1])} for x in m][-p["limit"]:]
            if path == "/futures/data/globalLongShortAccountRatio":
                pts = [x for x in m if x[0] // HOUR % 4 == 3][-p["limit"]:]
                return [{"timestamp": (x[0] // (4 * HOUR) + 1) * 4 * HOUR, "longAccount": str(x[2] / 100),
                         "longShortRatio": str(x[2] / (100 - x[2]))} for x in pts]
            if path == "/futures/data/topLongShortPositionRatio":
                pts = [x for x in m if x[0] // HOUR % 4 == 3][-p["limit"]:]
                return [{"timestamp": (x[0] // (4 * HOUR) + 1) * 4 * HOUR, "longShortRatio": str(x[3])} for x in pts]
            if path == "/futures/data/takerlongshortRatio":
                return [{"buySellRatio": "0.98"}]
            raise AssertionError(path)
        return get

    def test_collector_end_to_end(self):
        import binance_collector as bc
        from datetime import datetime, timezone
        hist = make_history(300, 5)
        T = T0 + 290 * DAY + 5 * HOUR
        now = datetime.fromtimestamp((T + 30 * 60_000) / 1000, timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            summary = {"generated_at": now.isoformat(), "period": {}, "params": {}, "base": {},
                       "per_coin": {}, "tested": 1,
                       "validated": [{"id": "trend_up_1d", "desc_tr": "x", "direction": "long", "effect": "olumlu",
                                      "rate_true": 70, "rate_false": 60, "lift_pp": 10, "n_true": 100,
                                      "liq_rate_true": 1}]}
            Path(tmp, "backtest_summary.json").write_text(json.dumps(summary))

            class FakeDT(datetime):
                @classmethod
                def now(cls, tz=None):
                    return now
            with mock.patch.object(bc, "DATA_DIR", Path(tmp)), \
                    mock.patch.object(bc, "get", self.fake_api(hist, T)), \
                    mock.patch.object(bc, "datetime", FakeDT), \
                    mock.patch("builtins.print"):
                self.assertEqual(self._run(bc), 0)
            latest = json.loads(Path(tmp, "latest.json").read_text())
        self.assertEqual(latest["errors"], {})
        c = latest["coins"][0]
        for k in ("atr_pct_1d", "ema50_1d", "funding_pctl_30d", "global_long_pct_pctl_30d",
                  "oi_change_7d_pct", "spot_imbalance_24h", "prev_day_high", "conditions_true"):
            self.assertIsNotNone(c.get(k), k)
        self.assertEqual(c["funding_interval_h"], 8)
        self.assertEqual(latest["evidence"]["status"], "ok")
        self.assertIsInstance(latest["btc_trend_up_1d"], bool)
        self.assertEqual(bool(c["evidence_hits"]), "trend_up_1d" in c["conditions_true"])
        self.assertEqual(latest["feature_time"][11:16], "05:00")

    def _run(self, bc):
        with mock.patch.object(sys, "argv", ["x", "BTCUSDT"]):
            return bc.main()

    def test_live_and_backtest_features_match(self):
        """Aynı T için canlı yol (API biçimi) ve backtest yolu aynı koşulları üretmeli."""
        import binance_collector as bc
        import backtest as bt
        hist = make_history(300, 6)
        T = T0 + 290 * DAY + 5 * HOUR
        get = self.fake_api(hist, T)
        with mock.patch.object(bc, "get", get):
            _, f_live, _ = bc.snapshot("BTCUSDT", get("/fapi/v1/premiumIndex")[0],
                                       get("/fapi/v1/ticker/24hr")[0], T)
        with tempfile.TemporaryDirectory() as tmp:
            write_history(Path(tmp), "BTCUSDT", hist)
            with mock.patch.object(bt, "HIST_DIR", Path(tmp)):
                s = bt.load_symbol("BTCUSDT")
        iT = s["fut_idx"][T]
        jd = bt.bisect_left(s["daily_t"], T - DAY + 1)
        js = s["spot_idx"][T]
        f_bt = fx.compute_features(s["fut"][iT - fx.N_1H:iT], s["daily"][jd - fx.N_1D:jd], T,
                                   spot=s["spot"][js - 30:js], oi=s["oi"], longp=s["longp"],
                                   top=s["top"], funding=s["funding"])
        for k in ("ret_24h", "range_24h", "ema50_1d", "ema200_1d", "atr_pct_1d", "ema20_4h",
                  "oi_chg_24h", "long_pct", "long_pct_pctl_30d", "top_ratio_pctl_30d",
                  "funding_8h", "funding_pctl_30d", "spot_imb_24h", "perp_taker_ratio_24h"):
            self.assertIsNotNone(f_bt.get(k), k)
            self.assertAlmostEqual(f_live[k], f_bt[k], places=4, msg=k)


if __name__ == "__main__":
    unittest.main()
