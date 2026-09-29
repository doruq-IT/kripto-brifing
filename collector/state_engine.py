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

Gönderim: değişiklik varsa detaylı mesaj (her saat, gece dahil). Değişiklik yoksa
QUIET_START–QUIET_END (00:00–08:00 TSİ) dışında tek satırlık özet, gece hiçbir şey.

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
QUIET_START, QUIET_END = 0, 8  # TSİ saat; bu aralıkta değişiklik yoksa mesaj yok
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


def parts(c):
    """Mesajda gösterilen ölçüler (Türkçe biçimli)."""
    out = {
        "range": f"aralık %{tr_num(c['range_24h_pct'])}",
        "long": f"long %{tr_num(c['global_long_pct'])}",
        "oi": f"OI {tr_pct(c['oi_change_24h_pct'])}",
        "chg": f"24s {tr_pct(c['change_24h_pct'])}",
    }
    if c.get("liq_distance_in_atr") is not None:
        out["liq"] = f"liq {tr_num(c['liq_distance_in_atr'])} gün"
    return out


def assess(c):
    """Tek coin → (seviye, gerekçe metni, etiketler, ölçü satırı) veya veri eksikse None.

    Gerekçe: seviyeyi belirleyen ölçüler. Ölçü satırı: geri kalan ölçüler.
    """
    rng, lp = c.get("range_24h_pct"), c.get("global_long_pct")
    oi, chg = c.get("oi_change_24h_pct"), c.get("change_24h_pct")
    if None in (rng, lp, oi, chg):
        return None
    conds = set(c.get("conditions_true") or [])
    tags = [t for cid, t in TAGS if cid in conds]
    red = [k for k, hit in (("range", rng >= 10), ("oi", abs(oi) >= 15), ("chg", chg <= -5)) if hit]
    if red:
        level, why = "🔴", red
    elif rng <= 5 and lp < 70 and abs(oi) < 10:
        level, why = "🟢", []
    else:
        level = "🟡"
        why = [k for k, hit in (("long", lp >= 70), ("range", rng > 5), ("oi", abs(oi) >= 10)) if hit]
    pt = parts(c)
    rest = " · ".join(pt[k] for k in ("range", "long", "oi", "liq") if k in pt and k not in why)
    return level, ", ".join(pt[k] for k in why), tags, rest


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
        level, why, tags, rest = a
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
        if st["level"] == level:
            view[coin] = (st["level"], why, tags, rest)
        else:  # iyileşme teyit bekliyor: eski seviyede, güncel ölçülerle
            view[coin] = (st["level"], f"düzeliyor, şu an {level}", tags, rest)

    recovered = not prev.get("data_ok", True)
    if first or changes or recovered:
        return state, render(latest, now, view, changes, missing, first, recovered)
    if QUIET_START <= now.astimezone(TSI).hour < QUIET_END:
        return state, None
    return state, summary(now, view, missing)


def summary(now, view, missing):
    """Değişiklik olmayan saatlerin tek satırlık özeti."""
    out = [f"🕐 {now.astimezone(TSI).strftime('%H:%M')} TSİ", "değişiklik yok"]
    for lvl in ("🟢", "🟡", "🔴"):
        coins = sorted((k for k, v in view.items() if v[0] == lvl), key=_key)
        if coins:
            out.append(f"{lvl} " + " ".join(coins))
    if missing:
        out.append("veri yok: " + " ".join(sorted(missing, key=_key)))
    return " · ".join(out)


def _key(coin):
    return COIN_ORDER.index(coin) if coin in COIN_ORDER else len(COIN_ORDER)


LEVEL_HEAD = {
    "🟢": "🟢 SAKİN — hareket 5x kurgun için sakin",
    "🟡": "🟡 TEMKİNLİ — bir ölçü sınırda",
    "🔴": "🔴 SERT — hareket 5x kurgun için fazla sert",
}
LEGEND = [
    "Seviyeler yönden bağımsız: long ve short tutan için aynı risk. Yön bilgisi değildir.",
    "Aralık = 24s en yüksek-en düşük farkı (🟢 ≤%5, 🔴 ≥%10; 5x'te ~%20 ters hareket liq). "
    "Long = long hesap oranı (≥%70 kalabalık long: ters harekette long tutanlar için toplu liq riski). "
    "OI = açık pozisyon 24s değişimi (🟡 ±%10, 🔴 ±%15). 24s ≤ -%5 düşüş de 🔴. "
    "Liq gün = 5x liq mesafen kaç günlük ortalama hareket (küçükse risk yüksek).",
]


def green_history(latest):
    """Backtest'te 🟢 filtresinin long liq oranı (doğrulanmış ya da zayıf işaret) → satır veya None."""
    ev = latest.get("evidence") or {}
    if ev.get("status") != "ok":
        return None
    days = (ev.get("period") or {}).get("days")
    for key, label in (("validated", "doğrulanmış"), ("weak", "zayıf işaret, kanıt değil")):
        for c in ev.get(key) or []:
            if c.get("id") == "filter_green" and c.get("direction") == "long" \
                    and c.get("liq_rate_true") is not None and c.get("liq_rate_false") is not None:
                return (f"Geçmiş {days} gün: 🟢 durumda açılan long'larda liq %{tr_num(c['liq_rate_true'])}, "
                        f"diğer durumlarda %{tr_num(c['liq_rate_false'])} ({label}).")
    return None


def coin_line(coin, why, tags, rest):
    head = coin + "".join(tags)
    if why:
        return f"{head}: neden {why}" + (f" | {rest}" if rest else "")
    return f"{head}: {rest}"


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
        L.append("")
        L.append("Değişen:")
        for coin, old, new, why, tags in sorted(changes, key=lambda x: _key(x[0])):
            arrow = f"{old} → {new}" if old else f"yeni: {new}"
            L.append(f"• {coin}{''.join(tags)} {arrow}" + (f", neden {why}" if why else ""))
    used_tags = set()
    for lvl in ("🟢", "🟡", "🔴"):
        coins = sorted((k for k, v in view.items() if v[0] == lvl), key=_key)
        if not coins:
            continue
        L.append("")
        L.append(LEVEL_HEAD[lvl])
        for coin in coins:
            _, why, tags, rest = view[coin]
            used_tags.update(tags)
            L.append(coin_line(coin, why, tags, rest))
    if missing:
        L.append("Veri yok: " + ", ".join(sorted(missing, key=_key)))
    L.append("")
    if used_tags:
        L.append(" · ".join(f"{t} {TAG_LEGEND[t]}" for t in TAG_LEGEND if t in used_tags))
    L.extend(LEGEND)
    gh = green_history(latest)
    if gh:
        L.append(gh)
    L.append("Bilgi amaçlı, işlem önerisi değil.")
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
