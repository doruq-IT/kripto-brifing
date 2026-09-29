# Kripto Brifing — Proje Durumu ve Devam Rehberi

> Son güncelleme: 29.09.2026, ~14:00 TSİ (sabah routine v2 kaydedildi)
> Bu dosya projeye yeni bir Claude oturumunda kaldığı yerden devam etmek için hazırlandı. Yeni oturumda bu dosyayı ver ve "buradan devam edelim" de.

> ⚠️ Bu repo **herkese açık** (GitHub'dan şifresiz clone edilebiliyor). Bu dosyaya ve repoya IP adresi, SSH portu, token, chat ID, API anahtarı, sunucudaki diğer servislerin ayrıntıları veya güvenlik açıkları **yazılmamalı**.

---

## 0. Hızlı özet

- **Sabah brifingi (Claude Routine, 08:47 TSİ):** Telegram kanalına 11 maddelik kripto brifingi. Binance verisini VPS'in GitHub'a yayınladığı `latest.json`'dan okur (bulut ortamı Binance'e erişemiyor, HTTP 451).
- **Saatlik risk durumu (VPS, her saat :30):** 29.09'da canlıya alındı. Her coin için 🟢/🟡/🔴 risk seviyesi, aynı Telegram kanalına. Değişiklik varsa detaylı mesaj, yoksa gündüz tek satır özet, gece (00–08 TSİ) sessiz. **Yön sinyali değildir.**
- **Backtest (VPS, her pazar):** Okan'ın kurgusunu (5x, %2 TP, SL yok, 96 saat) **2 yıl**, 11 coin, **4 saatte bir giriş** ile simüle eder; 38 koşulu × 2 yön = 76 testi Bonferroni düzeltmeli (%99,93) blok-bootstrap ile sınar.
- **29.09 ana bulgu:** 2 yılda **0/76** koşul doğrulandı. Filtresiz kurgu iki yönde de zararda (long −0,68, short −0,37 USDT/işlem). 28.09'da "doğrulanmış" sanılan iki short koşulu (24s ≤ −%5 düşüş, long tasfiyesi) sadece 09:00 TSİ girişine özgü çıktı, geniş testte tutmadı. Binance verisinden **tutarlı yön sinyali yok**; veri sadece **risk** hakkında bilgi veriyor (kalabalık long kötü, 🟢 günlerde liq daha düşük — zayıf işaret düzeyinde).
- Bu yüzden saatlik sistem "muhtemelen long/short" yerine **risk durumu** olarak kuruldu (Okan'ın kararı, 29.09).
- Brifing ve saatlik mesaj hiçbir koşulda al/sat tavsiyesi, giriş seviyesi veya hedef fiyat vermez.

---

## 1. Kaldığımız yer (29.09.2026)

### Yapılan adımlar

| # | Adım | Durum |
|---|---|---|
| 1 | Hazırlık: repo yerelde clone, kod okundu | ✅ |
| 2 | Toplayıcı: prim/basis, sıkışma (Bollinger genişliği) | ✅ canlıda |
| 3 | Backtest: 2 yıl, 4 saatlik giriş, Bonferroni, zayıf işaret katmanı, 9 yeni aday koşul | ✅ canlıda (0/76 doğrulanmış, 3 zayıf işaret) |
| 4 | Saatlik risk durumu → Telegram (sabah brifingiyle aynı kanal) | ✅ canlıda |
| 5 | Sabah routine'ini yenilemek (tek mesaj, Gündem, "Dünden", biriken düzeltmeler) | ✅ 29.09 routine'e kaydedildi; **30.09 ilk çalışma kontrol edilecek** |
| 6 | Önemli gelişmede VPS'in routine'i API ile çağırması (günde en fazla 2–3) | ⏳ |

### Hemen teyit edilecek

- Sunucuda `git pull` ile `68636b2` (saatlik tek satır özet) alındı mı, testler `OK` mi? Okan'a komut verildi, sonucu henüz gelmedi:
  ```bash
  cd /opt/kripto-brifing && git pull -q && git log --oneline -1 && python3 -m unittest discover -s collector/tests 2>&1 | tail -1
  ```
- İlk :30 çalışmasından sonra kanala tek satır özet ya da detaylı mesaj geldi mi? Log: `tail -5 /var/log/kripto-brifing.log` → `durum motoru: mesaj` veya `değişiklik yok`.
- 30.09 sabah brifingi: 10. madde artık "📈 kanıt yok / 📉 kanıt yok / ⚪ 11 coin / Filtresiz: long −0,68, short −0,37 (son 727 gün)" yazmalı. Mevcut prompt bu durumu doğru işliyor olmalı; kontrol et.

### Yarım kalan kararlar / notlar

- Sunucu artık **`claude/durum-motoru`** branch'inde çalışıyor (eski: `claude/elegant-cori-lln6rd`). main'e merge edilmedi.
- Sunucuda eski 1 yıllık geçmiş veri yedek olarak duruyor: `collector/data/history1y_yedek/`. Deneme klasörleri: `collector/data/deneme`, `deneme2y`, `deneme2y95` (silinebilir).
- 5. adımda (sabah routine'i) prompt'a girecek biriken düzeltmeler için bkz. §9.

---

## 2. Mimari

```
                      saatlik (:30)                          curl (raw URL)
┌───────────────────────────────┐  push -f  ┌──────────────────────────────┐ ◄──────── ┌─────────────────────────────┐
│ VPS (okan-vps)                │ ────────► │ GitHub doruq-IT/kripto-brifing│           │ Claude Routine              │
│ publish.sh                    │ deploy key│ branch: market-data           │           │ "Kripton Karar Sabah        │
│  ├ binance_collector.py       │           │  ├ latest.json                │           │  Brifingi" 08:47 TSİ        │
│  │  └ features.py             │           │  ├ backtest_report.txt        │           │ + Crypto.com, alternative.me│
│  └ state_engine.py ──► notify.py ─────────────────────────────────┐        │ + web arama → Telegram      │
│ weekly_backtest.sh (Pazar)    │           └──────────────────────────────┘ │        └─────────────────────────────┘
│  ├ history_download.py        │                                            ▼
│  └ backtest.py                │                                   Telegram kanalı (aynı kanal)
└───────────────────────────────┘                                   ← saatlik risk durumu (VPS)
                                                                    ← sabah brifingi (routine)
```

- Brifingin okuduğu adres: `https://raw.githubusercontent.com/doruq-IT/kripto-brifing/market-data/latest.json`
- Backtest raporu: `https://raw.githubusercontent.com/doruq-IT/kripto-brifing/market-data/backtest_report.txt`
- `market-data` her yayında tek commit olarak yeniden yazılır. Yerel geçmiş VPS'te `snapshots.jsonl`.
- Zamanlama: özellikler saat başında (`feature_time`), yayın ve durum motoru her saatin 30. dakikasında (Binance OI verisi saat başından ~25 dk sonra geliyor). Brifing 05:47 UTC'de 05:30 yayınını okur.

---

## 3. GitHub reposu

- Repo: `doruq-IT/kripto-brifing` (public)
- **Güncel kod branch'i: `claude/durum-motoru`** (sunucu bunu çalıştırıyor). `claude/elegant-cori-lln6rd`'nin devamı. main'e merge edilmedi, PR açılmadı.
- Veri branch'i: `market-data` (VPS yazar, elle dokunulmaz).
- Okan'ın Windows makinesinde yerel clone: `E:\Kripton gezegeni\Kripto Araştırma\kripto-brifing` (Claude buradan push edebiliyor; HTTPS kimlik bilgisi Windows'ta kayıtlı). Yerelde Python 3.14 ve 3.12 var; testler `PYTHONUTF8=1 py -3.12 -m unittest discover -s collector/tests` ile (Windows'ta UTF-8 modu gerekli). Sunucu Python 3.10 — 3.11+ özelliği kullanılmamalı.

```
kripto-brifing/
├── README.md
├── PROJE_DURUMU.md               # Bu dosya
├── collector/
│   ├── binance_collector.py      # Saatlik canlı toplayıcı (public API, stdlib)
│   ├── features.py               # Özellik + koşul tanımları — canlı ve backtest ORTAK
│   ├── state_engine.py           # Saatlik risk durumu (29.09)
│   ├── notify.py                 # Telegram gönderimi, kimlik bilgisi repo dışında (29.09)
│   ├── history_download.py       # Backtest geçmiş verisi (+ prim endeksi, 29.09)
│   ├── backtest.py               # Simülasyon, koşul testleri, zayıf işaret, SL karşılaştırması
│   ├── weekly_backtest.sh        # history_download + backtest (DAYS=730)
│   ├── publish.sh                # Toplayıcı + durum motoru + market-data push
│   ├── tests/test_pipeline.py    # 40 test (sentetik veri)
│   └── data/                     # (git'e girmez)
└── briefing/
    └── routine_prompt.txt        # Routine prompt'unun birebir kaydı (29.09'da güncel hâliyle eşitlendi)
```

### 29.09 commit'leri

| Commit | İçerik |
|---|---|
| `648738c` | Prim z-skoru, sıkışma, 9 aday koşul, 4 saatlik backtest girişi, dinamik Bonferroni |
| `6054fd6` | Durum motoru + notify, 2 yıllık backtest varsayılanı, zayıf işaret katmanı |
| `84edafc` | Risk mesajı: coin başına ölçüler, "neden" önce, yönden bağımsız açıklama, 🟢 geçmiş satırı |
| `68636b2` | Değişiklik yoksa tek satır özet, 00–08 TSİ sessiz |
| (bu commit) | PROJE_DURUMU.md, README, routine_prompt.txt güncel hâl |

---

## 4. Toplanan veri — `latest.json`

11 coin (USDT perpetual): **BTC, ETH, BNB, SOL, XRP, ADA, AVAX, LINK, LTC, BCH, SUI** (`binance_collector.py` → `DEFAULT_SYMBOLS`).

### Üst düzey alanlar

| Alan | Anlamı |
|---|---|
| `generated_at` | Yayın zamanı (UTC). Brifing 3 saatten eskiyse, durum motoru 2 saatten eskiyse kullanmaz |
| `feature_time` | Özelliklerin hesaplandığı saat başı (UTC) |
| `btc_trend_up_1d` | BTC günlük EMA50 üstünde mi |
| `coins[]`, `errors{}` | Coin bazında alanlar / hatalar |
| `evidence` | Backtest özeti: `status`, `period`, `params`, `base`, `per_coin`, `tested`, `validated[]`, **`weak[]`** (29.09), `sl_summary`. 14 günden eskiyse `status` "eski" |
| `direction_summary` | Doğrulanmış kanıtın coin bazında gruplanmış hâli. 0 doğrulanmış olduğu için şu an tüm coinler `no_evidence` |

### Coin alanları

| Alan | Kaynak |
|---|---|
| price, change_24h_pct, high_24h, low_24h, range_24h_pct, quote_volume_24h_usdt | `/fapi/v1/ticker/24hr` |
| mark_price, funding_rate_pct, next_funding_time, **basis_pct** (mark/index − 1, %) | `/fapi/v1/premiumIndex` |
| funding_interval_h, funding_8h_equiv_pct, funding_pctl_30d, funding_avg_7d_8h_pct | `/fapi/v1/fundingRate` |
| oi_usdt, oi_change_4h/24h/7d_pct | `/futures/data/openInterestHist` |
| global_long_short_ratio, global_long_pct, global_long_pct_pctl_30d | `/futures/data/globalLongShortAccountRatio` |
| top_trader_position_ls_ratio, top_trader_ratio_pctl_30d | `/futures/data/topLongShortPositionRatio` |
| taker_buy_sell_ratio | `/futures/data/takerlongshortRatio` |
| ema20/50/200_1d, dist_ema50/200_1d_pct, atr_pct_1d, liq_distance_in_atr, tp2_in_atr, prev_day_high/low, high_7d/low_7d, ret_7d_pct, **bbw_1d_pct, bbw_pctl_90d** | `/fapi/v1/klines` 1d |
| trend_4h, perp_taker_ratio_24h, perp_imbalance_24h | `/fapi/v1/klines` 1h |
| spot_imbalance_24h, spot_perp_volume_ratio | `/api/v3/klines` |
| **premium_pct, premium_z7d** (prim endeksi, 7 günlük z-skoru) | `/fapi/v1/premiumIndexKlines` 1h |
| conditions_true, conditions_unknown, evidence_hits, warnings | `features.py` |

- `liq_distance_in_atr` = 19,5 / ATR%. BTC ≈ 7, BCH/SUI ≈ 2,5–2,7.
- `bbw_pctl_90d`: bugünkü Bollinger bant genişliğinin son 90 gündeki yüzdelik sırası (≤10 = sıkışma).
- 29.09 örnek: prim %−0,08 ile %+0,05 arası (normal); bant genişliği yüzdelikleri 60–100 (oynaklık yüksek).

---

## 5. Koşullar (features.py → CONDITIONS, 38 adet)

Canlı ve backtest aynı kodu kullanır. 29 eski koşul + 29.09'da **önceden kaydedilen** 9 aday (test sonucuna bakılarak tanım değiştirilmez):

| id | Açıklama | Grup |
|---|---|---|
| `trend_conflict` | günlük trend (EMA50) ile 4 saatlik trend çelişiyor | kararsız |
| `squeeze` | Bollinger genişliği 90 günün en düşük %10'unda | kararsız |
| `premium_high` | prim 7 günlük ortalamanın ≥ +2 std üstünde | long riski |
| `up_aligned` | fiyat EMA50 ve EMA200 üstünde, 4s trend yukarı | yukarı adayı |
| `up_healthy_oi` | up_aligned + fiyat ↑ + OI 0 ile +%10 | yukarı adayı |
| `up_not_crowded` | up_healthy_oi + funding pctl < 80 + long < %70 | yukarı adayı |
| `up_btc_confirm` | up_not_crowded + BTC EMA50 üstünde | yukarı adayı |
| `down_aligned` | fiyat EMA50 altında, 4s trend aşağı | aşağı adayı |
| `down_shorts_building` | down_aligned + fiyat ↓ + OI ≥ +%5 | aşağı adayı |

Eski 29 koşul (özet): trend_up_1d, above_ema200_1d, trend_up_4h, ret7d_pos, drop_5pct_24h, pump_5pct_24h, wide_range_24h, near_day_low/high, high_vol, funding_high/low/negative, oi_up_10, oi_down_10, long_crowd_70, long_pctl_high/low, top_pctl_high/low, perp_sellers/buyers, spot_leads, shorts_building, crowded_long_rally, long_flush, btc_trend_up, filter_green, filter_red.

---

## 6. Backtest — yöntem (29.09 hâli)

- **Veri:** 2 yıl + ısınma (`DAYS=730`). Futures/spot 1h mum, funding, prim endeksi: Binance API. OI/long/top trader: `data.binance.vision` metrics arşivi. İndirme sadece ileri doğru ekler; `DAYS` büyütülürse boş bir `HIST_DIR`'e sıfırdan indirilmeli (29.09'da böyle yapıldı: `history2y` → `history`).
- **Simülasyon:** her coin için `STEP_H=4` saatte bir özellik (01, 05, 09, 13, 17, 21 UTC), bir sonraki saatin açılışında long ve short. 5x isolated, 50 USDT marj, TP +%2, SL yok, liq −%19,5, en fazla 96 saat, ücret %0,05×2, funding dahil, eklemesiz. Aynı mumda TP ve ters seviye → ters seviye önce (kötümser). `STEP_H=24` eski günlük kurguyu verir.
- **Koşul testi:** koşul doğru/yanlış işlem başı PnL farkı; haftalık blok bootstrap (`BOOT=10000`); aralık düzeyi = 100 − 5/test sayısı (76 test → %99,934); iki yarıda aynı yön; en az `MIN_N` = 60×24/STEP_H = 360 işlem ve 30 farklı gün.
- **Zayıf işaret (29.09):** %95 aralık sıfırı içermiyor + iki yarıda aynı yön, düzeltme yok. Raporda "3b" bölümü ve `evidence.weak`. **Kanıt değildir**; 76 testte tesadüfen 1–2 beklenir.
- Süre: VPS'te 2 yıllık tam backtest ~3 dk.
- Parametreler: `DAYS, STEP_H, TP_PCT, ADV_PCT, LIQ_PCT, HOLD_H, MARGIN, LEV, FEE_PCT, BOOT, MIN_N, CI_LEVEL, SL_GRID, SL_SLIP, FEATURE_HOUR, ENTRY_HOUR, HIST_DIR, DATA_DIR`.

---

## 7. Bulgular

### 7.1 Karşılaştırma

| Test | Dönem | Giriş | Doğrulanan | Filtresiz long | Filtresiz short |
|---|---|---|---|---|---|
| 28.09 (eski) | 1 yıl | günde 1 (09:00 TSİ) | 2/58 (ikisi short) | −1,48 | +0,18 |
| 29.09 deneme | 1 yıl | 4 saatte bir | 0/76 | −1,29 | +0,10 |
| **29.09 canlı** | **2 yıl (2024-09-29 → 2026-09-25)** | **4 saatte bir** | **0/76** | **−0,68** | **−0,37** |

- 2 yılda başa baş için gereken TP oranı ~%78; gerçekleşen long %73,0, short %74,8. Kazanç/kayıp yapısı (+5 / −50) yön fark etmeksizin kurguyu zorluyor.
- Eski "short lehine" bulguları geniş testte tutmadı: `drop_5pct_24h` short +0,93/+0,05, yarılar −0,10/+1,42; `long_flush` short +0,61/+0,06, yarılar −0,14/+0,83.

### 7.2 Zayıf işaretler (2 yıl, %95)

| Koşul | Long PnL doğru/yanlış | Liq doğru/yanlış | Not |
|---|---|---|---|
| `long_crowd_70` | −1,19 / −0,29 | %3,6 / %1,6 | 1 yıllık testte de aynı yön → en güvenilir |
| `filter_green` | −0,13 / −0,91 | %1,0 / %3,1 | 1 yıllık testte de aynı yön |
| `wide_range_24h` | +0,32 / −0,83 | %3,1 / %2,4 | 1 yıllık testte tutarsız; şüpheli |

Hiçbiri yön bilgisi değil; hepsi long'da riski azaltan/artıran durumlar.

### 7.3 1 yıllık denemede dikkat çeken (kanıt değil)

- `squeeze` long: +0,67 / −1,68, liq %1,2 / %2,7, yarılar +2,19/+1,99; short'ta −2,39. Sıkışmada long'un liq riski düşük — arkadaşın "sıkışma veto olsun" önerisinin tersi.
- `trend_conflict` long: 0,00 / −1,70, liq %0,5 / %3,1.
- Yeni `up_*` trend zinciri long'da işe yaramadı (`up_not_crowded` −2,18).

### 7.4 SL (28.09'dan, değişmedi)

Karar (Okan, 28.09): şimdilik SL yok. `sl_summary` anlamlı iyileşme göstermedikçe brifing stop'tan bahsetmez.

---

## 8. Saatlik risk durumu (state_engine.py)

### Kurallar

- Seviye = sabah brifingi 8. madde ile birebir (backtest'te `filter_green`/`filter_red`):
  - 🔴 SERT: 24s aralık ≥ %10 VEYA |OI 24s| ≥ %15 VEYA 24s değişim ≤ −%5
  - 🟢 SAKİN: 24s aralık ≤ %5 VE long hesap < %70 VE |OI 24s| < %10
  - 🟡 TEMKİNLİ: geri kalanlar
- Etiketler (seviyeyi değiştirmez): 👥 kalabalık long (`long_crowd_70`), 〰️ trend çelişkisi, 💸 prim yüksek, 🌀 sıkışma.
- Histerezis: kötüleşme hemen; iyileşme 2 saat üst üste görülürse. Teyit beklerken "neden düzeliyor, şu an 🟢" yazar.
- Gönderim: değişiklik varsa detaylı mesaj (gece dahil); yoksa 08:00–24:00 TSİ tek satır özet, 00:00–08:00 hiçbir şey. İlk çalışma ve veri geri gelince detaylı.
- Veri 2 saatten eski / okunamıyorsa bir kez "güncellenemedi" uyarısı.
- Telegram gönderilemezse durum kaydedilmez, bir sonraki saat tekrar denenir.
- Kuru çalıştırma: `DRY_RUN=1` veya kimlik bilgisi yoksa mesaj sadece log'a basılır.

### Mesaj örnekleri

Detaylı (değişiklik/ilk rapor):
```
🕐 Risk Durumu — 29.09 13:02 TSİ (veri 12:00)
İlk durum raporu.

🟢 SAKİN — hareket 5x kurgun için sakin
BTC: aralık %2,2 · long %56,4 · OI -%1,6 · liq 7,1 gün
...
🟡 TEMKİNLİ — bir ölçü sınırda
ETH👥: neden long %70,5 | aralık %3,7 · OI +%3,7 · liq 5,6 gün
...
🔴 SERT — hareket 5x kurgun için fazla sert
LINK: neden aralık %16,6, OI +%19,4 | long %66,8 · liq 3,5 gün

👥 kalabalık long
Seviyeler yönden bağımsız: long ve short tutan için aynı risk. Yön bilgisi değildir.
Aralık = ... (eşik açıklamaları)
Geçmiş 727 gün: 🟢 durumda açılan long'larda liq %1,0, diğer durumlarda %3,1 (zayıf işaret, kanıt değil).
Bilgi amaçlı, işlem önerisi değil.
```
Değişiklik yoksa:
```
🕐 14:31 TSİ · değişiklik yok · 🟢 BTC BNB SOL BCH · 🟡 ETH XRP ADA LTC SUI · 🔴 AVAX LINK
```

### Kimlik bilgileri

- Sunucuda repo dışında, izin 600: `/etc/kripto-brifing.env` → `KRIPTO_TG_TOKEN`, `KRIPTO_TG_CHAT` (sabah routine'iyle aynı bot ve kanal). Değerler asla repoya, log'a veya sohbete yazılmaz.
- Durum hafızası: `collector/data/state.json` (silinirse bir sonraki çalışma "İlk durum raporu" gönderir).

---

## 9. Sabah routine'i

### 29.09 öğleden sonra yapılanlar (güncel hâl)

- **Tek mesaj** (iki mesaj kararı geri alındı, Okan): 🟢/🟡/🔴 grupları ve liq radarı saatlik mesajda olduğu için brifingten çıktı. Sıra: 🌍 Piyasa, ⏮️ Dünden, 📰 Gündem (≤3), 🪙 Coinlerimiz, ⏰ Bugün takipte, 🇹🇷 Türkiye, 📊 Türev (📡 BTC/ETH + uç coin, 📍 seviyeler, 🧭 Yön tek satır), ⚠️ Bugün dikkat, ❓ Yarın bakılacak. ~2500 birim, sınır 3500.
- Kararlar (Okan, 29.09): fiyatlar hepsi Binance (Crypto.com yedek); profil satırı ~%78 / ~%91 / gerçekleşen ~%73-75; 🔴 asimetrisi şimdilik değişmedi (metin "-%5 sadece düşüşe bakar" diyor); zayıf işaret satırı tek mesajda çıkarıldı (saatlik mesajda 👥 ve 🟢 geçmiş satırı var).
- Yeni kaynak: CoinGecko `/api/v3/global` (dominans, hacim). Ortamın allowed domains listesine `api.coingecko.com` eklendi (Okan; henüz çalışmada doğrulanmadı).
- **Dünden hafızası:** `claude/brifing-hafiza` branch'i (orphan, sadece `sorular.json`). Routine mesajdan sonra soruları buraya push eder, ertesi sabah raw URL'den okur. Cevaplar "Evet / Hayır / Henüz sonuçlanmadı" (isabet değil: soruya beklenti koymak yön tahmini olurdu). Routine'e repo bağlandı (29.09, Okan, UI'da prompt kutusunun altındaki "Select a repository").
- Claude artık routine'i `RemoteTrigger` aracıyla **okuyabiliyor** (prompt, repo, sonraki çalışma, çalışma kayıtları: `list_runs` / `get_run_log`). Ortamın allowed domains listesi bu araçla görünmüyor.
- Deneme bu oturumda yapıldı (Telegram'a gönderilmeden).
- **29.09 13:57 manuel çalışma (v2 ilk canlı):** repo klonlandı, CoinGecko erişildi, mesaj gitti (2792 karakter), `sorular.json` push edildi (3 soru, tarih 2026-09-29) → 30.09 brifinginde ⏮️ Dünden ilk kez dolu gelmeli. Bulunan iki hata prompt'ta düzeltildi (`92dbbbb`, routine'e yapıştırıldı ve birebir doğrulandı): LINK funding işareti ters yazıldı (+%0,0037 → -%0,0037; düşük yüzdelik "negatif" sanıldı) ve bugünkü JOLTS/Conference Board takvimden kaçtı (tek arama) → artık en az 3 takvim araması.

### Eski plan (29.09 sabah; iki mesaj kısmı geçersiz)

- Ad: **Kripton Karar Sabah Brifingi**, ID `trig_01Swxrg8zfpKMCuTfTBUAMJU`, `47 5 * * *` UTC (08:47 TSİ), bağlayıcı: Crypto.com. Telegram: routine ortamındaki `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
- ⚠️ Routine `http_api` ile oluşturulduğu için Claude güncelleyemez. Claude `briefing/routine_prompt.txt`'yi güncelleyip push eder ve **tam metni** sohbete yazar; Okan yapıştırır.
- ⚠️ **Pro plan: günde 5 routine çalışması.** "Run now" da büyük ihtimalle kotadan düşer (resmi dokümanda açık değil, bağımsız kaynak "düşer" diyor). Prompt denemeleri routine'de değil, normal Claude oturumunda yapılmalı (Telegram'a göndermeden metni göstererek).
- Güncel prompt: `briefing/routine_prompt.txt` (29.09'da Okan'ın verdiği son hâl ile eşitlendi).

### Kararlaştırılan yeni yapı (29.09)

**İki mesaj**, aynı çalışmada arka arkaya:

*Mesaj 1 — ☀️ Gündem:*
1. Piyasa: BTC/ETH + 11 coinin öne çıkanları, BTC dominansı, toplam hacim, korku-açgözlülük, ABD vadelileri/DXY/10Y tek satır
2. ⏮️ Dünden: dünkü 2–3 takip sorusu ve sonucu ("İsabet / Henüz sonuçlanmadı / Tutmadı")
3. 📰 Gündem: en fazla 3–4 haber, 🔴/🟡 önem etiketi, kaynak adı, tek kaynaklıysa "doğrulanmadı"
4. 🪙 Coinlerimiz: 11 coinden sadece önemli haberi olanlar (yoksa satır yok)
5. ⏰ Bugün takipte (TSİ, saat sıralı): ABD makro, Fed konuşmacıları, diğer merkez bankaları (ECB/BoJ/BoE), token unlock'lar (dolaşımdaki arzın %'si ile), ETF karar tarihleri, opsiyon vadesi (cuma; ay/çeyrek sonu büyük), ağ güncellemeleri, ABD borsa açılışı
6. 🇹🇷 Türkiye (SPK, vergi, TL) — yoksa "yeni gelişme yok"
7. ❓ Yarın bakılacak: 2–3 somut, ölçülebilir soru (ertesi gün "Dünden" bunları cevaplar)

*Mesaj 2 — 📊 Türev ve kuralların:* mevcut 4, 7, 8, 9, 10, 11. maddelerin sıkıştırılmış hâli.

**"Dünden" hafızası:** routine soruları repoda bir `claude/` branch'ine küçük bir dosya olarak yazar, ertesi sabah okur (routine'ler `claude/` branch'lerine her zaman push edebilir). Sadece piyasa soruları, kişisel veri yok. Uygulamadan önce routine ortamının repoya yazma erişimi doğrulanmalı (routine'e repo eklenmesi gerekebilir).

Örnek alınan trader brifinginden alınanlar: Dünden (isabet kontrolü), haber önem etiketi, saat sıralı takvim, Türkiye satırı, dominans/hacim. Alınmayanlar: kurala bağlı olmayan genel risk cümleleri, ABD sayı biçimi, doğrulanmamış kaynak.

### Prompt'a girecek biriken düzeltmeler

1. **10. madde:** 0 doğrulanmış olduğu için artık hep "kanıt yok" + filtresiz ortalama yazacak. İsteğe bağlı: `evidence.weak`'ten tek satır "zayıf işaret (kanıt değil)" eklenebilir — karar verilmedi. Stop notu kuralı aynen kalır.
2. **8. madde asimetrisi:** 🔴 kuralında sadece "24s ≤ −%5" var, "yönden bağımsız" deniyor ama +%5 pump dahil değil. Düzeltmek `features.py` → `filter_red` ve state_engine'i de değiştirir (backtest yeniden). Henüz karar yok.
3. **8. maddede öncelik:** "Önce 🔴, sonra 🟢, kalanlar 🟡" açıkça yazılmalı (kod zaten böyle).
4. **Veri eskilik sınırı:** 3 saat → 2 saat (saatlik yayın; durum motoru 2 saat kullanıyor).
5. **Fiyat kaynağı karışıklığı:** 1. maddede Crypto.com fiyat/high-low, 7–8. maddelerde Binance aralığı → çelişebilir. Seçenek: her şeyi Binance'ten almak. Karar Okan'da.
6. **Kullanılmayan alan tanımları:** prompt'ta tanımlanıp kullanılmayan alanlar (top_trader_*, taker_buy_sell_ratio, oi_change_4h/7d, conditions_true, evidence_hits, btc_trend_up_1d) sadeleştirilebilir ya da 4. maddeye bağlanabilir. Yeni alanlar (premium_z7d, bbw_pctl_90d, basis_pct) istenirse eklenebilir.
7. **10. madde satır sınırı:** 8 satır tam dolabiliyor; satır önceliği yazılmalı.
8. **Telegram karakter sayımı:** Telegram emojileri 2 birim sayar, `wc -m` 1 sayar; iki mesaja bölününce sorun kalmaz.
9. **Profil satırı:** "Başa baş için ~%91 isabet" eklemeli kurguya göre; eklemesiz 2 yıllık backtest'te gereken ~%78, gerçekleşen ~%73–75. İstenirse güncellenebilir.

---

## 10. Araştırma özeti (29.09) — yön/risk kriterleri

| Kriter ailesi | Literatür | Bizim sonucumuz |
|---|---|---|
| Trend/momentum (EMA, 1–4 hafta getiri) | Güçlü ama haftalık ufuk, çöküş riski (Liu & Tsyvinski, RFS) | %2 TP / 1–4 gün ufkunda işe yaramadı |
| Kalabalık/aşırı pozisyon (funding, basis, long ≥%70) | Yüksek basis çöküşleri öngörüyor (BIS WP 1087 / Management Science) — tail risk, ortalama yön değil | %70 kuralı zayıf işaret (long kötü) |
| OI + fiyat 4 durumu | Pratik lore, akademik kanıtı zayıf | "Long tasfiyesi = dip" inancının tersi 1 yılda görüldü, 2 yılda tutmadı |
| Taker akışı | Gerçek ama dakikalar–12 saat, ~0,5 bp (ücret 5 bp) | Doğrulanmadı |
| Oynaklık rejimi | Çok güçlü (oynaklık kümelenir) | Yüksek oynaklık long liq'ini artırıyor; sıkışmada long liq düşük |
| Takvim/saat | Zayıf | Test edilmedi |

**Arkadaşın 4 önerisinin değerlendirmesi:** (1) Basis — fikir doğru (eklendi), ama "Mark − Spot" tanımı ve "fiyat düşmese de stop olursun" SL'siz ve mark-price liq'li kurguda geçerli değil. (2) 5–15 dk taker oranı — kurgu için yanlış ve kendi içinde çelişkili (emilim = taker > 1 iken fiyatın gitmemesi). (3) Likidasyon havuzları — olgu gerçek ama haritalar model tahmini, ücretsiz geçmişi yok, backtest edilemez; eklenmedi. (4) ATR vetosunu tersine çevirmek — stop kullanan trader için yazılmış; Okan'da yüksek ATR liq mesafesini kısaltıyor; sıkışma ek aday olarak eklendi.

**Routine limitleri (resmi doküman):** Pro 5/gün, Max 15/gün, Team/Enterprise 25/gün; en kısa aralık 1 saat; tek seferlik zamanlanmış çalışmalar kotaya dahil değil; API tetikleyicisi (`/fire`) mevcut. Saatlik routine bu yüzden imkânsız → saatlik iş VPS'te.

---

## 11. VPS (sunucu) tarafı

Sunucu: **okan-vps** (Ubuntu 22.04, Python 3.10, root). IP/SSH bilgileri Okan'da. Aynı sunucudaki diğer servislere dokunulmaz; brifing onlardan bağımsız.

| Yol | Ne |
|---|---|
| `/opt/kripto-brifing/` | Repo clone'u (branch: **`claude/durum-motoru`**) |
| `collector/data/latest.json`, `snapshots.jsonl` | Son snapshot / saatlik geçmiş |
| `collector/data/state.json` | Durum motoru hafızası |
| `collector/data/history/<COIN>/` | Backtest verisi (2 yıl): fut_1h, spot_1h, funding, premium_1h, metrics (+ metrics_raw) |
| `collector/data/history1y_yedek/` | Eski 1 yıllık veri (yedek) |
| `collector/data/backtest_summary.json`, `backtest_report.txt` | Canlı backtest çıktıları |
| `collector/data/deneme*/` | 29.09 deneme çıktıları (silinebilir) |
| `/etc/kripto-brifing.env` | Telegram kimlik bilgileri (600) |
| `/opt/kripto-brifing-publish/` | publish.sh'in geçici git klasörü |
| `~/.ssh/kripto_brifing_deploy` | GitHub deploy key (yazma yetkili) |
| `/var/log/kripto-brifing.log` | Saatlik cron (durum motoru satırı + `yayınlandı: HH:MMZ`) |
| `/var/log/kripto-brifing-backtest.log` | Haftalık backtest |

### Cron (root crontab, değişmedi)

```
30 * * * * /bin/bash /opt/kripto-brifing/collector/publish.sh >> /var/log/kripto-brifing.log 2>&1
15 2 * * 0 /bin/bash /opt/kripto-brifing/collector/weekly_backtest.sh >> /var/log/kripto-brifing-backtest.log 2>&1
```
İlk otomatik 2 yıllık backtest: 04.10.2026 pazar 02:15 UTC.

### Sık kullanılan komutlar

```bash
# Kod güncellemesi (:35–:25 arası; :30 cron'uyla çakışmasın)
cd /opt/kripto-brifing && git pull -q && git log --oneline -1
python3 -m unittest discover -s collector/tests 2>&1 | tail -3

# Toplayıcıyı yayınlamadan çalıştır
python3 collector/binance_collector.py

# Durum motorunu kuru çalıştır (gönderme)
DRY_RUN=1 python3 collector/state_engine.py

# Durum hafızasını sıfırla ve tam rapor gönder
rm -f collector/data/state.json && python3 collector/state_engine.py

# Backtest (canlı) ve rapor
python3 collector/backtest.py > /dev/null && sed -n '1,2p;/^3) DOĞRULANMIŞ/,/^4)/p' collector/data/backtest_report.txt

# Deneme klasöründe backtest (canlıyı etkilemez)
mkdir -p collector/data/deneme && DATA_DIR=collector/data/deneme python3 collector/backtest.py > /dev/null

# Uzun işler: arka planda ve -u ile (çıktı anında log'a düşsün)
nohup bash -c 'python3 -u collector/backtest.py > /dev/null' > /tmp/bt.log 2>&1 &

# Loglar
tail -20 /var/log/kripto-brifing.log
```

Eski branch'e dönüş (acil durum): `cd /opt/kripto-brifing && git checkout claude/elegant-cori-lln6rd` (durum motoru devre dışı kalır).

---

## 12. Okan'ın profili

- Kasa ~500 USDT; sadece futures, 5x isolated, işlem başı 50 USDT marj, en fazla 5 pozisyon, gün içi–3/4 gün tutar.
- TP %10 ROE (≈%2 fiyat). SL yok (28.09 kararı). Liq'e yakın bir kez ekleme. 5x'te ~%20 ters hareket = liq.
- Sadece büyük ve stabil coinler.
- Plan: Claude **Pro**.
- Brifing/saatlik mesaj **al/sat tavsiyesi vermez.**

---

## 13. Alınan kararlar ve gerekçeleri

| Karar | Gerekçe |
|---|---|
| Proxy ile Binance'e erişim yok | Binance şartlarına aykırı |
| Veri VPS'te toplanır, GitHub'a yayınlanır | Bulut ortamı HTTP 451 |
| Canlı ve backtest aynı `features.py` | Brifingte aktif koşul = test edilen koşul |
| Doğrulama ölçütü PnL | Temiz kazanç oranı oynaklıkta yanıltıcı |
| **Saatlik iş VPS'te, routine'de değil** (29.09) | Pro 5 çalışma/gün; saatlik = 24 |
| **Adaylar test öncesi kaydedildi** (29.09) | Sonuca bakıp kural seçmek sahte kanıt üretir |
| **Backtest 4 saatlik giriş** (29.09) | Saatlik motor günün her saatinde çalışıyor; tek saat örneklemi yanıltıcıydı |
| **Bonferroni test sayısından** (29.09) | 76 test; %99,93 |
| **2 yıllık veri** (29.09) | 1 yılda güç düşük; yarılar = iki farklı yıl |
| **Zayıf işaret ayrı katman, kanıt değil** (29.09) | Bilgi kaybolmasın ama kanıt diye sunulmasın |
| **Saatlik sistem = risk durumu, yön değil** (29.09, Okan) | 2 yılda yön sinyali doğrulanmadı |
| **Vetolar seviyeyi ezmez, etiket** (29.09) | Doğrulanmış sinyal 🔴 içinde kalabiliyordu |
| **Kötüleşme hemen, iyileşme 2 saat** (29.09) | Sınırda gidip gelmeyi önler, riski geciktirmez |
| **Değişince detay, yoksa tek satır, gece sessiz** (29.09, Okan) | Sistemin çalıştığı görünür, kanal boğulmaz |
| **Saatlik mesaj sabah brifingiyle aynı kanal** (29.09, Okan) | Tek kanal |
| **Telegram kimlik bilgisi `/etc/kripto-brifing.env`** | Repo public |
| **Likidasyon haritası eklenmedi** | Model tahmini, geçmişi yok, test edilemez |
| **Sabah brifingi iki mesaj** (29.09) | İçerik 3800'e sığmaz; gündem ve türev ayrı |
| SL yok (şimdilik) | 28.09 SL analizi |
| **Haber puanı risk seviyesine girmez** (29.09, Okan) | Geçmişe dönük test edilemez, LLM puanı tutarsız, yön sinyaline kayar; zamanlanmış olaylar sabah ⏰ satırında zaten var, saatlik 📅 etiketi gereksiz bulundu. Açık kalan fikir: "makro veri günü" (CPI/FOMC/istihdam) aday koşul olarak backtest'e (liq oranı farkı) |

---

## 14. Sıradaki adımlar

1. ✅ Sunucu `68636b2`, testler OK; saatlik mesaj kanala geliyor; 10:30Z yayınından itibaren `evidence` 2 yıllık (0/76, 3 zayıf).
2. **30.09 sabah brifingini kontrol et** (`RemoteTrigger list_runs` → `get_run_log`): tek mesaj gitti mi, CoinGecko erişildi mi, `sorular.json` `claude/brifing-hafiza`'ya push edildi mi, 🧭 satırı "kanıt yok" + long -0,68 / short -0,37 mi. 01.10'da ⏮️ Dünden satırının dolduğunu kontrol et.
3. ⏰ bölümü için ücretsiz ve buluttan erişilebilir unlock/ETF/opsiyon kaynağı (şimdilik web araması).
4. **6. adım — Aşama C:** VPS olağan dışı hareket görürse (1 saatte sert fiyat hareketi, OI sıçraması, funding uç değeri) routine'in API tetikleyicisini çağırır; Claude haberleri araştırıp kısa "ne oldu" mesajı yazar. Pro'da günde en fazla 2–3 çağrı + bekleme süresi. Yeni routine gerekir (API trigger, token sunucuda env dosyasında).
5. 04.10 ilk otomatik 2 yıllık backtest raporunu oku.
6. Opsiyonel: kurgu parametre taraması (TP/tutma süresi/kaldıraç) — işlem önerisi değil, geçmiş veride ne olduğunu gösterir; eklemeli kurguyu simüle etmek; `claude/durum-motoru`'yu main'e merge etmek; deneme klasörlerini temizlemek.

---

## 15. Sorun giderme

| Belirti | Olası neden / çözüm |
|---|---|
| Brifingte "Binance verisi alınamadı" | `generated_at` eski. `tail /var/log/kripto-brifing.log`; `bash collector/publish.sh` |
| Kanalda "Risk durumu güncellenemedi" | Aynı neden; veri gelince "Veri yeniden geliyor" mesajı otomatik gelir |
| Saatlik mesaj hiç gelmiyor | Log'da `durum motoru` satırı var mı? `KURU ÇALIŞTIRMA` yazıyorsa env dosyası eksik/okunamıyor: `ls -l /etc/kripto-brifing.env` ve §8 kontrol komutu |
| `telegram: HTTP 400/401/403` | Token/chat yanlış veya bot kanalda yönetici değil |
| 10. madde "backtest verisi yok" | `evidence.status` ok değil; `tail -40 /var/log/kripto-brifing-backtest.log` |
| Toplayıcıda `UYARI: prim/klines/funding/spot` | Opsiyonel uç geçici başarısız; temel veri yine yayınlanır |
| `nohup` log'u boş kalıyor | Python çıktıyı tamponluyor; `python3 -u` kullan veya dosyalara bak |
| Windows'ta testler `UnicodeEncodeError` | `PYTHONUTF8=1` ile çalıştır |
| Cron çalışmıyor | `crontab -l \| grep kripto` iki satır göstermeli |

---

## 16. Yeni oturumda nasıl devam edilir

Yeni Claude oturumunda (yerel klasör `E:\Kripton gezegeni\Kripto Araştırma\kripto-brifing`, branch `claude/durum-motoru`) şunu yaz:

> `PROJE_DURUMU.md` dosyasını oku. Kripto brifing projesine kaldığımız yerden devam edeceğiz. [yapmak istediğin şey]

Çalışma kuralları (oturmuş düzen):
- Claude VPS'e bağlanamaz: komutları yazar, Okan çalıştırıp çıktıyı yapıştırır. Adım adım, her adımdan sonra çıktı kontrol edilir. Karar gerektiğinde Claude zamanı gelince sorar.
- Claude Binance'e erişemez; `market-data` branch'indeki dosyaları okuyarak doğrular.
- Claude routine'i güncelleyemez: `briefing/routine_prompt.txt`'yi güncelleyip push eder ve tam metni sohbete yazar.
- Kod değişikliği push edilmeden önce testler çalıştırılır; yeni davranış için test eklenir. Sunucu Python 3.10.
- Sunucuda `git pull` sadece `collector/` değiştiğinde gerekir; :30 cron'uyla çakışmaması için :35–:25 arası.
- Uzun sunucu işleri `nohup` + `python3 -u` ile arka planda.
- İddialar veriyle desteklenir; doğrulanmamış sonuç kanıt olarak sunulmaz. Aday kurallar test öncesi sabitlenir.
- Token/chat ID asla repoya, log'a veya sohbete yazılmaz.
- Brifing ve saatlik mesaj hiçbir koşulda al/sat tavsiyesi, giriş seviyesi veya hedef fiyat vermez.
