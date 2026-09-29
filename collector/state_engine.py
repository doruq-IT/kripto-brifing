#!/usr/bin/env python3
"""Saatlik risk durumu: latest.json'dan her coinin risk seviyesini hesaplar, bir önceki
durumla karşılaştırır ve değişiklik varsa Telegram mesajı gönderir.

Seviye, sabah brifingindeki 8. madde ile birebir aynı kurallardır (backtest'te
filter_green / filter_red olarak test edilir):
  🔴 24s aralık ≥ %10 VEYA |OI 24s| ≥ %15 VEYA 24s değişim ≤ -%5
  🟢 24s aralık ≤ %5 VE long hesap < %70 VE |OI 24s| < %10
  🟡 geri kalanlar
Etiketler seviyeyi değiştirmez, sadece bilgi verir: 👥 kalabalık long, 〰️ trend
çelişkisi, 💸 prim yüksek, 🌀 sıkışma.

Histerezis: kötüleşme (🟢→🟡, 🟡→🔴) hemen bildirilir; iyileşme ancak yeni seviye
IMPROVE_HOURS (2) saat üst üste görülürse kabul edilir. Böylece sınırda gidip gelen
bir coin her saat mesaj üretmez.

Bu bir yön/işlem sinyali değildir. 2 yıllık backtest'te Binance verisinden tutarlı
bir yön sinyali bulunamadı; mesaj bunu açıkça yazar.

Kullanım (publish.sh her saat çağırır):
  python3 state_engine.py            # hesapla, değişiklik varsa gönder
  DRY_RUN=1 python3 state_engine.py  # göndermeden mesajı ekrana bas
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import notify  # noqa: E402

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parent / "data"))
STATE_FILE = "state.json"
IMPROVE_HOURS = 2
MAX_DATA_AGE_H = 2
TSI = timezone(timedelta(hours=3))
RANK = {"🟢": 0, "🟡": 1, "🔴": 2}
COIN_ORDER = ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "AVAX", "LINK", "LTC", "BCH", "SUI"]
TAGS = [  # (koşul id, etiket)
    ("long_crowd_70", "👥"),
    ("trend_conflict", "〰️"),
    ("premium_high", "💸"),
    ("squeeze", "🌀"),
]
TAG_LEGEND = {"👥": "kalabalık long", "〰️": "günlük/4s trend çelişkisi", "💸": "vadeli prim yüksek",
              "🌀": "oynaklık sıkışması"}


def tr_num(v, nd=1, sign=False):
    s = f"{v:+.{nd}f}" if sign else f"{v:.{nd}f}"
    return s.replace(".", ",")


def tr_pct(v, nd=1):
    """-3,2 → '-%3,2'; 4 → '+%4,0'"""
    return ("-" if v < 0 else "+") + "%" + tr_num(abs(v), nd)


def assess(c):
    """Tek coin → (seviye, gerekçe metni, etiketler) veya veri eksikse None."""
    rng, lp = c.get("range_24h_pct"), c.get("global_long_pct")
    oi, chg = c.get("oi_change_24h_pct"), c.get("change_24h_pct")
    if None in (rng, lp, oi, chg):
        return None
    red = []
    if rng >= 10:
        red.append(f"aralık %{tr_num(rng)}")
    if abs(oi) >= 15:
        red.append(f"OI {tr_pct(oi)}")
    if chg <= -5:
        red.append(f"24s {tr_pct(chg)}")
    conds = set(c.get("conditions_true") or [])
    tags = [t for cid, t in TAGS if cid in conds]
    if red:
        return "🔴", ", ".join(red), tags
    if rng <= 5 and lp < 70 and abs(oi) < 10:
        return "🟢", "", tags
    why = []
    if lp >= 70:
        why.append(f"long %{tr_num(lp)}")
    if rng > 5:
        why.append(f"aralık %{tr_num(rng)}")
    if abs(oi) >= 10:
        why.append(f"OI {tr_pct(oi)}")
    return "🟡", ", ".join(why), tags


def step(prev, latest, now):
    """Saf fonksiyon: (önceki durum, latest.json, şimdi) → (yeni durum, mesaj|None).

    Durum: {"coins": {coin: {"level", "since", "pending", "pending_n"}}, "data_ok": bool}
    """
    prev = prev or {}
    pcoins = prev.get("coins", {})
    state = {"coins": {}, "data_ok": True, "updated": now.isoformat(timespec="minutes")}
    try:
        gen = datetime.fromisoformat(latest["generated_at"])
        age_h = (now - gen).total_seconds() / 3600
        coins = latest.get("coins") or []
    except Exception:
        age_h, coins = None, []
    if age_h is None or age_h > MAX_DATA_AGE_H or not coins:
        state["coins"] = pcoins
        state["data_ok"] = False
        if prev.get("data_ok", True):  # sadece ilk bozulmada bir kez uyar
            why = "dosya okunamadı" if age_h is None else (
                "coin verisi boş" if not coins else f"veri {age_h:.1f} saat eski")
            return state, f"⚠️ Risk durumu güncellenemedi: {why}. Veri gelince tekrar bildirilecek."
        return state, None

    first = not pcoins
    changes, view, missing = [], {}, []
    for c in coins:
        coin = c["symbol"].replace("USDT", "")
        a = assess(c)
        if a is None:
            missing.append(coin)
            if coin in pcoins:
                state["coins"][coin] = pcoins[coin]
            continue
        level, why, tags = a
        p = pcoins.get(coin)
        if p is None:
            st = {"level": level, "since": state["updated"], "pending": None, "pending_n": 0}
            if not first:
                changes.append((coin, None, level, why, tags))
        elif RANK[level] > RANK[p["level"]]:  # kötüleşme: hemen
            st = {"level": level, "since": state["updated"], "pending": None, "pending_n": 0}
            changes.append((coin, p["level"], level, why, tags))
        elif RANK[level] < RANK[p["level"]]:  # iyileşme: IMPROVE_HOURS saat üst üste
            n = p["pending_n"] + 1 if p.get("pending") == level else 1
            if n >= IMPROVE_HOURS:
                st = {"level": level, "since": state["updated"], "pending": None, "pending_n": 0}
                changes.append((coin, p["level"], level, why, tags))
            else:
                st = {**p, "pending": level, "pending_n": n}
        else:
            st = {**p, "pending": None, "pending_n": 0}
        state["coins"][coin] = st
        view[coin] = (st["level"], why if st["level"] == level else "düzeliyor", tags)

    recovered = not prev.get("data_ok", True)
    if not (first or changes or recovered):
        return state, None
    return state, render(latest, now, view, changes, missing, first, recovered)


def _key(coin):
    return COIN_ORDER.index(coin) if coin in COIN_ORDER else len(COIN_ORDER)


def render(latest, now, view, changes, missing, first, recovered):
    ft = latest.get("feature_time")
    try:
        data_h = datetime.fromisoformat(ft).astimezone(TSI).strftime("%H:%M")
    except Exception:
        data_h = "?"
    L = [f"🕐 Risk Durumu — {now.astimezone(TSI).strftime('%d.%m %H:%M')} TSİ (veri {data_h})"]
    if first:
        L.append("İlk durum raporu.")
    elif recovered and not changes:
        L.append("Veri yeniden geliyor.")
    if changes:
        L.append("Değişen:")
        for coin, old, new, why, tags in sorted(changes, key=lambda x: _key(x[0])):
            arrow = f"{old} → {new}" if old else f"yeni: {new}"
            extra = " ".join(x for x in (why, "".join(tags)) if x)
            L.append(f"• {coin} {arrow}" + (f" ({extra})" if extra else ""))
    used_tags = set()
    for lvl in ("🟢", "🟡", "🔴"):
        items = []
        for coin in sorted((k for k, v in view.items() if v[0] == lvl), key=_key):
            _, why, tags = view[coin]
            used_tags.update(tags)
            s = coin + "".join(tags)
            if why and lvl != "🟢":
                s += f" ({why})"
            items.append(s)
        if items:
            L.append(f"{lvl} " + ", ".join(items))
    if missing:
        L.append("Veri yok: " + ", ".join(sorted(missing, key=_key)))
    if used_tags:
        L.append(" · ".join(f"{t} {TAG_LEGEND[t]}" for t in TAG_LEGEND if t in used_tags))
    L.append("🟢 kurallarınla çelişmiyor · 🟡 temkinli · 🔴 hareket kurgun için sert")
    L.append("Yön: 2 yıllık veride tutarlı yön sinyali yok. Bilgi amaçlı, işlem önerisi değil.")
    return "\n".join(L)


def main():
    now = datetime.now(timezone.utc)
    sp = DATA_DIR / STATE_FILE
    try:
        prev = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else None
    except Exception:
        prev = None
    try:
        latest = json.loads((DATA_DIR / "latest.json").read_text(encoding="utf-8"))
    except Exception:
        latest = {}
    state, msg = step(prev, latest, now)
    if msg:
        ok = notify.send(msg)
        if not ok and not notify.dry_run():
            # Gönderilemediyse durumu kaydetme: bir sonraki saat aynı değişiklik tekrar denenir
            print("durum motoru: mesaj gönderilemedi, durum kaydedilmedi", file=sys.stderr)
            return 1
    tmp = sp.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(sp)
    print(f"durum motoru: {'mesaj' if msg else 'değişiklik yok'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
