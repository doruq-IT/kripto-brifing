# Kripto Brifing — Proje Durumu ve Devam Rehberi

> Son güncelleme: 28.09.2026, ~23:00 TSİ
> Bu dosya projeye yeni bir Claude oturumunda kaldığı yerden devam etmek için hazırlandı. Yeni oturumda bu dosyayı ver ve "buradan devam edelim" de.

> ⚠️ Bu repo **herkese açık** (GitHub'dan şifresiz clone edilebiliyor). Bu dosyaya ve repoya IP adresi, SSH portu, token, chat ID, API anahtarı, sunucudaki diğer servislerin ayrıntıları veya güvenlik açıkları **yazılmamalı**.

---

## 0. Hızlı özet

- Her sabah 08:47 TSİ'de bir Claude Routine, Okan'ın Telegram kanalına **11 maddelik kripto brifingi** gönderir.
- Binance verisi Okan'ın **VPS'inde** saatlik toplanır ve GitHub'daki `market-data` branch'ine yayınlanır. Bulut ortamı Binance'e erişemediği için (HTTP 451) brifing veriyi oradan okur.
- VPS her pazar **backtest** çalıştırır: Okan'ın işlem kurgusunu (5x, %2 TP, SL yok) son 1 yılda simüle eder, 29 koşulu **işlem başı PnL** açısından istatistiksel olarak test eder. Brifingteki "Yön özeti" (10. madde) **sadece doğrulanmış** koşullara dayanır; kanıt yoksa bunu açıkça yazar.
- İlk bulgular: filtresiz long bu dönemde zarar etti (işlem başı −1,48 USDT). Doğrulanan 2 koşulun ikisi de sert düşüş sonrası **short** tarafında. Sıkı SL bu kazancı yok ediyor. Karar: şimdilik **SL yok**.
- Brifing hiçbir koşulda al/sat tavsiyesi, giriş seviyesi veya hedef fiyat vermez. "Lehine" dili kullanılır.

---

## 1. Projenin amacı

Okan'ın her sabah Telegram'a gelen **"Kripton Karar Sabah Brifingi"** mesajını:
1. Binance Futures türev verileriyle (funding, açık pozisyon, long/short oranları, trend, oynaklık) zenginleştirmek,
2. Okan'ın işlem kurallarına göre sade, telefonda tek okuyuşta anlaşılır bir dille yazdırmak,
3. "Veri varsa göster, yoksa yok de" ilkesiyle geçmiş veride **doğrulanmış** yön bilgisini eklemek.

**Temel kısıt:** Brifing Claude'un bulut ortamında çalışıyor ve Binance bu ortamı engelliyor (**HTTP 451**, "restricted location"). Proxy veya Cloudflare ile atlatmak **bilerek tercih edilmedi**, çünkü Binance kullanım şartlarına aykırı ve güvenilmez.

**Çözüm:** Veriyi Okan'ın VPS'i toplar ve GitHub'a yayınlar; brifing oradan okur.

---

## 2. Mimari

```
                 saatlik (:30)                         curl (raw URL)
┌──────────────────────────┐  push -f   ┌──────────────────────────────┐  ◄────────  ┌─────────────────────────────┐
│ VPS (okan-vps)           │ ─────────► │ GitHub doruq-IT/kripto-brifing│            │ Claude Routine              │
│ publish.sh               │ deploy key │ branch: market-data           │            │ "Kripton Karar Sabah        │
│  └ binance_collector.py  │            │  ├ latest.json                │            │  Brifingi" 08:47 TSİ        │
│     └ features.py        │            │  ├ backtest_report.txt        │            │ + Crypto.com bağlayıcısı    │
│ weekly_backtest.sh (Paz) │            │  └ backtest_summary.json      │            │ + alternative.me, web arama │
│  ├ history_download.py   │            └──────────────────────────────┘            │ → Telegram                  │
│  └ backtest.py           │                                                         └─────────────────────────────┘
└──────────────────────────┘
```

- Brifingin okuduğu adres: `https://raw.githubusercontent.com/doruq-IT/kripto-brifing/market-data/latest.json`
- Backtest raporu (Claude buradan okuyabilir): `https://raw.githubusercontent.com/doruq-IT/kripto-brifing/market-data/backtest_report.txt`
- `market-data` branch'i her yayında **tek commit** olarak yeniden yazılır, geçmiş şişmez. Yerel geçmiş VPS'te `snapshots.jsonl` içinde kalır.
- Zamanlama: özellikler saat başında hesaplanır (`feature_time`), yayın her saatin 30. dakikasında yapılır. Brifing 05:47 UTC'de 05:30 yayınını okur (05:00 UTC verisi). Backtest de tam olarak bu anı (05:00 UTC) simüle eder.

---

## 3. GitHub reposu

- Repo: `doruq-IT/kripto-brifing`
- **Kod branch'i: `claude/elegant-cori-lln6rd`.** Tüm güncel geliştirme burada. Eski `claude/binance-api-connection-test-4omj2z` branch'inin devamıdır. main'e merge edilmedi, PR açılmadı.
- VPS bu branch'te çalışıyor.
- Veri branch'i: `market-data`. İçinde `latest.json`, `backtest_report.txt`, `backtest_summary.json` var. VPS otomatik yazar, elle dokunulmaz.

```
kripto-brifing/
├── README.md                     # Mimari + VPS kurulum adımları
├── PROJE_DURUMU.md               # Bu dosya
├── .gitignore                    # collector/data/ ve __pycache__ hariç
├── collector/
│   ├── binance_collector.py      # Saatlik canlı toplayıcı (public API, sadece stdlib)
│   ├── features.py               # Özellik + koşul tanımları — canlı ve backtest ORTAK kullanır
│   ├── history_download.py       # Backtest geçmiş verisi (Binance API + data.binance.vision metrics arşivi)
│   ├── backtest.py               # Kurgu simülasyonu, koşul testleri, SL karşılaştırması
│   ├── weekly_backtest.sh        # history_download + backtest (haftalık cron)
│   ├── publish.sh                # Toplayıcı + latest.json ve backtest çıktılarını market-data'ya push
│   ├── tests/test_pipeline.py    # 22 test (sentetik veri): göstergeler, simülasyon, SL, parse, uçtan uca
│   └── data/                     # (git'e girmez) latest.json, snapshots.jsonl, history/, backtest_*
└── briefing/
    └── routine_prompt.txt        # Routine prompt'unun birebir kaydı
```

Testler: `python3 -m unittest discover -s collector/tests -v`

---

## 4. Toplanan veri — `latest.json`

Varsayılan 11 coin (USDT perpetual): **BTC, ETH, BNB, SOL, XRP, ADA, AVAX, LINK, LTC, BCH, SUI**. Liste `binance_collector.py` → `DEFAULT_SYMBOLS` içinde.

### Üst düzey alanlar

| Alan | Anlamı |
|---|---|
| `generated_at` | Yayın zamanı (UTC). Brifing 3 saatten eskiyse Binance verisini kullanmaz |
| `feature_time` | Özelliklerin hesaplandığı saat başı (UTC) |
| `btc_trend_up_1d` | BTC günlük EMA50 üstünde mi |
| `coins[]` | Coin bazında alanlar (aşağıda) |
| `errors{}` | Coin bazında hata; boş olmalı |
| `evidence` | Backtest özeti: `status` ("ok" / "eski (N gün)" / yok), `period`, `params`, `base` (filtresiz long/short), `per_coin`, `tested`, `validated[]`, `sl_summary`. 14 günden eskiyse `status` "eski" olur ve brifing kanıt kullanmaz |
| `direction_summary` | Doğrulanmış kanıtın coin bazında gruplanmış hâli: `long_favored`, `short_favored`, `long_weaker`, `short_weaker`, `no_evidence`. 10. madde bunu yazar |

### Coin alanları ve kaynakları

| Alan | Kaynak |
|---|---|
| price, change_24h_pct, high_24h, low_24h, range_24h_pct, quote_volume_24h_usdt | `/fapi/v1/ticker/24hr` |
| mark_price, funding_rate_pct, next_funding_time | `/fapi/v1/premiumIndex` |
| funding_interval_h (4 veya 8), funding_8h_equiv_pct, funding_pctl_30d, funding_avg_7d_8h_pct | `/fapi/v1/fundingRate` (31 gün) |
| oi_usdt, oi_change_4h_pct, oi_change_24h_pct, oi_change_7d_pct | `/futures/data/openInterestHist` (1h, 200 saat) |
| global_long_short_ratio, global_long_pct, global_long_pct_pctl_30d | `/futures/data/globalLongShortAccountRatio` (4h, 180 nokta = 30 gün) |
| top_trader_position_ls_ratio, top_trader_ratio_pctl_30d | `/futures/data/topLongShortPositionRatio` (4h, 180 nokta) |
| taker_buy_sell_ratio | `/futures/data/takerlongshortRatio` (4h) |
| ema20/50/200_1d, dist_ema50_1d_pct, dist_ema200_1d_pct, atr_pct_1d, liq_distance_in_atr, tp2_in_atr, prev_day_high/low, high_7d/low_7d, ret_7d_pct | `/fapi/v1/klines` 1d (259 kapanmış mum) |
| trend_4h, perp_taker_ratio_24h, perp_imbalance_24h | `/fapi/v1/klines` 1h (999 kapanmış mum) |
| spot_imbalance_24h, spot_perp_volume_ratio | `/api/v3/klines` spot 1h |
| conditions_true, conditions_unknown | `features.py` koşulları (bkz. §5) |
| evidence_hits | Bugün aktif olan **doğrulanmış** koşullar (yön, etki, PnL, liq, n) |
| warnings | Opsiyonel uç (klines, funding geçmişi, spot) alınamadıysa |

Notlar:
- Yüzdelikler (`*_pctl_30d`) değerin **coinin kendi** son 30 günündeki sırasıdır: 90 = son 30 günün en yüksek %10'u.
- Funding bazı coinlerde 4 saatte bir ödenir; karşılaştırma için 8 saatlik eşdeğere çevrilir. 28.09 itibarıyla 11 coinin hepsi 8 saatlikti.
- `liq_distance_in_atr` = 19,5 / ATR%, yani 5x liq mesafesinin kaç günlük ortalama hareket ettiği. BTC ≈ 7, BCH/SUI ≈ 2,7.
- Ek uçlardan biri başarısız olursa coin düşmez; temel alanlar yine yayınlanır, `warnings` doldurulur.
- OI zaman damgası doğrulandı: saat başındaki anlık değeri gösteriyor ve yaklaşık 25 dakika sonra yayınlanıyor. Backtest varsayımıyla aynı.

⚠️ Toplayıcıyı elle sembol vererek çalıştırmak (`binance_collector.py BNBUSDT ...`) yerel `latest.json`'ı sadece o coinlerle **ezer**. Bir sonraki cron 11 coinle düzeltir; GitHub'daki dosya sadece `publish.sh` çalışınca değişir.

---

## 5. Koşullar (features.py → CONDITIONS)

Her koşul T anında (saat başı) sadece o ana kadar bilinen veriden hesaplanır; geleceğe bakma yoktur. Canlı toplayıcı ve backtest **aynı kodu** kullanır. Pencere uzunlukları da eşittir (N_1H = 999, N_1D = 259) ve bunu bir test doğrular.

| id | Açıklama |
|---|---|
| `trend_up_1d` | fiyat günlük EMA50 üstünde |
| `above_ema200_1d` | fiyat günlük EMA200 üstünde |
| `trend_up_4h` | 4 saatlikte EMA20 > EMA50 |
| `ret7d_pos` | son 7 gün getirisi pozitif |
| `drop_5pct_24h` | 24 saatte -%5 veya daha fazla düşüş |
| `pump_5pct_24h` | 24 saatte +%5 veya daha fazla yükseliş |
| `wide_range_24h` | 24 saatlik aralık ≥ %10 |
| `near_day_low` | fiyat 24 saatlik aralığın alt çeyreğinde |
| `near_day_high` | fiyat 24 saatlik aralığın üst çeyreğinde |
| `high_vol` | günlük ATR ≥ %5 (yüksek oynaklık) |
| `funding_high` | funding kendi 30 gününün en yüksek %10'unda |
| `funding_low` | funding kendi 30 gününün en düşük %10'unda |
| `funding_negative` | funding negatif (short'lar ödüyor) |
| `oi_up_10` | açık pozisyon 24 saatte ≥ +%10 |
| `oi_down_10` | açık pozisyon 24 saatte ≤ -%10 |
| `long_crowd_70` | long hesap oranı ≥ %70 |
| `long_pctl_high` | long hesap oranı kendi 30 gününün en yüksek %10'unda |
| `long_pctl_low` | long hesap oranı kendi 30 gününün en düşük %10'unda |
| `top_pctl_high` | büyük hesapların long pozisyonu 30 günün en yüksek %10'unda |
| `top_pctl_low` | büyük hesapların long pozisyonu 30 günün en düşük %10'unda |
| `perp_sellers` | vadelide 24 saat agresif satıcı baskın (taker oranı < 0,95) |
| `perp_buyers` | vadelide 24 saat agresif alıcı baskın (taker oranı > 1,05) |
| `spot_leads` | spotta alım baskısı vadeliden güçlü |
| `shorts_building` | fiyat düşerken açık pozisyon ≥ +%5 (short birikimi olası) |
| `crowded_long_rally` | fiyat ve açık pozisyon artarken funding 30 günlük %80 üstü |
| `long_flush` | fiyat ≤ -%3 ve açık pozisyon ≤ -%5 (long tasfiyesi olası) |
| `btc_trend_up` | BTC günlük EMA50 üstünde |
| `filter_green` | brifingteki 🟢 filtresi |
| `filter_red` | brifingteki 🔴 filtresi |

---

## 6. Backtest — yöntem

**Veri** (`history_download.py`, VPS'te):
- Futures ve spot 1h mum, funding: Binance API. Canlı toplayıcıyla aynı uçlar.
- OI, global long %, top trader oranı: `data.binance.vision` günlük metrics arşivi. API bu verileri sadece son 30 gün için veriyor.
- Varsayılan süre 365 gün + ısınma (mumlarda 270 gün, metrics'te 32 gün). Tekrar çalıştırılınca sadece eksik kısmı indirir.
- Doğrulanan ilk indirme: coin başına 15.240 saatlik mum, 1.191 funding kaydı, 9.528 saatlik metrics satırı; eksik gün yok.

**Simülasyon** (`backtest.py`):
- Her gün her coin için 05:00 UTC özellikleri, 06:00 UTC açılışında long ve short sanal işlem.
- Kurgu: 5x isolated, 50 USDT marj (250 USDT pozisyon), TP +%2, SL yok, liq −%19,5, en fazla 96 saat, taker ücreti %0,05 × 2, funding ödemeleri dahil, **eklemesiz**.
- Mum içi sıra bilinmediği için aynı saatlik mumda TP ve ters seviye birlikte görülürse ters seviye önce sayılır (kötümser).
- Sonuç türleri: TP, liq, süre doldu (96 saat sonunda kapanıştan).

**Koşul testi:**
- Her koşul, long ve short için ayrı test edilir: koşul doğruyken ve yanlışken **işlem başı ortalama PnL** karşılaştırılır (29 koşul × 2 yön = 58 test).
- Güven aralığı: haftalık blok bootstrap (2.000 tekrar). Coinler aynı gün ve işlemler ardışık günlerde birbirine bağlı olduğu için yeniden örnekleme hafta bazında yapılır.
- Çoklu test düzeltmesi: %99,8 aralık kullanılır (58 test için Bonferroni'ye yakın).
- **Doğrulanmış** sayılmak için: PnL farkının aralığı sıfırı içermemeli, dönemin iki yarısında aynı yönde olmalı, koşul doğruyken en az 60 işlem ve 30 farklı gün olmalı.
- "Temiz kazanç" (ters yönde %10 görmeden TP) sadece bilgi olarak raporlanır. İlk çalıştırmada yüksek oynaklığın temiz kazancı artırıp liq'i de artırdığı ve PnL'i düşürdüğü görüldü; bu yüzden doğrulama PnL'e çevrildi.

**SL karşılaştırması:**
- Aynı işlemler stop'suz ve %2 / %3 / %5 / %8 / %10 fiyat stop'larıyla simüle edilir. Stop piyasa emriyle ve %0,05 kaymayla kapanır.
- Fark eşleştirilmiş (aynı işlem) haftalık bootstrap ile %95 aralıkta ve iki yarıda tutarlılıkla test edilir.
- Hem tüm işlemler hem her doğrulanmış koşul için ayrı ayrı yapılır.

**Doğrulama testleri** (sentetik veri):
- Veriye gömülen gerçek etki yakalandı (+16,9 pp).
- Saf gürültüde sahte kanıt çıkmadı.
- "Temiz oran yüksek ama PnL düşük" tuzağı doğru şekilde "olumsuz" sınıflandı.

**Çıktılar:** `data/backtest_summary.json` (toplayıcı okur), `data/backtest_report.txt` (5 bölüm: filtresiz sonuç, coin bazında, doğrulanmış koşullar, tüm koşullar, SL karşılaştırması).

**Parametreler** (ortam değişkeni): `DAYS`, `TP_PCT`, `ADV_PCT`, `LIQ_PCT`, `HOLD_H`, `MARGIN`, `LEV`, `FEE_PCT`, `BOOT`, `MIN_N`, `SL_GRID`, `SL_SLIP`, `FEATURE_HOUR`, `ENTRY_HOUR`.

---

## 7. Bulgular (ilk backtest: 2025-09-28 → 2026-09-24, 362 gün, 53 hafta)

### 7.1 Filtresiz kurgu (her gün her coinde, yön başına 3.982 işlem)

| | TP | Liq | 96 saatte sonuçsuz | İşlem başı | Toplam | Başa baş için gereken TP |
|---|---|---|---|---|---|---|
| Long | %68,0 | %2,6 | %29,4 | **−1,48 USDT** | −5.897 | %76,9 |
| Short | %74,8 | %1,9 | %23,4 | +0,18 USDT | +729 | %75,5 |

- 11 coinin **hepsinde** long ortalaması negatif. Yaklaşık her 38 long işlemde bir liq var ve tek liq yaklaşık 10 TP'yi siliyor.
- Bu tablo dönemin rejimine bağlıdır.

### 7.2 Doğrulanan koşullar (58 testten 2'si, PnL ölçütü)

| Koşul | Yön | İşlem başı (doğru / yanlış) | Aralık | Liq | n |
|---|---|---|---|---|---|
| 24 saatte ≤ −%5 düşüş (`drop_5pct_24h`) | short | +2,75 / +0,01 | [+0,35, +5,21] | %0,4 | 258 |
| Long tasfiyesi: fiyat ≤ −%3 ve OI ≤ −%5 (`long_flush`) | short | +2,32 / +0,01 | [+0,32, +5,22] | %0 | 296 |

- İkisi büyük ölçüde aynı olay: sert düşüşten sonra düşüş kısa vadede sürmüş. Aralığın alt ucu sıfıra yakın (+0,3); tek yıllık rejime bağlı olabilir.
- Aynı günlerde long daha kötü: düşüş sonrası liq %5,8, diğer günlerde %2,4. Anlamlı değil ama yön tutarlı; hata müzesindeki "dipten döner" ile örtüşüyor.

### 7.3 8. madde filtresi

- Hiçbir eşik değişikliği veriyle doğrulanmadı; filtre olduğu gibi kaldı.
- 🟢 long'da liq'i düşürüyor (%1,5'e karşı %3,2; işlem başı −0,78'e karşı −1,87). İki yarıda tutarlı ama anlamlı değil.
- %70 long kuralı yönsel olarak destekleniyor: long PnL farkı −1,23, aralık [−3,39, +0,69], iki yarıda tutarlı.
- Yüzdelik alternatifi (`long_pctl_high`) hiçbir fark göstermedi; mutlak %70 eşiği korunuyor.

### 7.4 SL karşılaştırması

| | Stop yok | %2 | %3 | %5 | %8 | %10 |
|---|---|---|---|---|---|---|
| Long, tüm işlemler (işlem başı) | −1,48 | −0,67 | −0,64 | −0,80 | −0,93 | −1,09 |
| Short, tüm işlemler | +0,18 | +0,04 | +0,11 | +0,14 | +0,18 | +0,28 |
| Short, sert düşüş sonrası | **+2,75** | +0,58 ✔− | +0,34 ✔− | +0,78 ✔− | +2,01 | +2,59 |
| Short, long tasfiyesi sonrası | **+2,32** | +0,37 ✔− | +0,32 ✔− | +0,36 ✔− | +1,33 ✔− | +1,96 |

(✔− = stop'suza göre anlamlı derecede **kötü**.)

- Long'da stop kaybı azaltıyor ama anlamlı değil ve long her seçenekte negatif. Sorun stop değil, giriş.
- Doğrulanmış short durumlarında sıkı stop kazancı yok ediyor: sert düşüş sonrası fiyat önce sıçrayıp stop'u alıyor, sonra TP'ye gidiyor.
- En kötü işlem: stop yok −50, %10 stop ≈ −26, %5 stop ≈ −13 USDT.
- **Karar (Okan, 28.09): şimdilik SL yok.** Seçenek olarak %10 "felaket stop'u" hazır: ortalamaya maliyeti anlamlı değil, en kötü kaybı yarıya indirir. 5 eş zamanlı liq −250 USDT (kasanın yarısı) iken %10 stop'la yaklaşık −128 olur; bu son hesap aritmetik, backtest'ten gelmiyor.
- Brifing stop'tan sadece `sl_summary` içinde anlamlı bir iyileşme olursa bahseder; şu an bahsetmiyor.

---

## 8. VPS (sunucu) tarafı

Sunucu: **okan-vps** (Ubuntu 22.04, Python 3.10, root). IP/SSH bilgileri Okan'da; bu public repoya yazılmaz.

Aynı sunucuda Okan'ın başka servisleri de çalışıyor. **Onlara dokunulmadı.** Brifing toplayıcısı onlardan tamamen bağımsızdır, host üzerinde cron ile çalışır, başka servislerin ayarlarını veya `.env`'ini kullanmaz.

### Klasör ve dosyalar

| Yol | Ne |
|---|---|
| `/opt/kripto-brifing/` | Repo clone'u (branch: `claude/elegant-cori-lln6rd`) |
| `/opt/kripto-brifing/collector/data/latest.json` | Son snapshot (yerel) |
| `/opt/kripto-brifing/collector/data/snapshots.jsonl` | Saatlik tüm geçmiş (her satır bir coin) |
| `/opt/kripto-brifing/collector/data/history/<COIN>/` | Backtest verisi: `fut_1h.csv`, `spot_1h.csv`, `funding.csv`, `metrics.csv`, `metrics_raw/*.zip` |
| `/opt/kripto-brifing/collector/data/backtest_summary.json` / `backtest_report.txt` | Son backtest çıktıları |
| `/opt/kripto-brifing-publish/` | `publish.sh`'in her seferinde silip yeniden oluşturduğu geçici git klasörü |
| `~/.ssh/kripto_brifing_deploy` (+ `.pub`) | GitHub deploy key (repo'ya **yazma yetkili**). Private key hiçbir yere kopyalanmamalı |
| `/var/log/kripto-brifing.log` | Saatlik cron çıktısı; her başarılı çalışmanın sonunda `yayınlandı: HH:MMZ` |
| `/var/log/kripto-brifing-backtest.log` | Haftalık backtest çıktısı |
| `/var/log/kripto-brifing-history.log` | İlk geçmiş veri indirmesinin çıktısı |

### Cron (root crontab)

Crontab'da başka servislere ait satırlar da var; onlara dokunulmaz. Bu projeye ait satırlar (28.09'da doğrulandı):

```
30 * * * * /bin/bash /opt/kripto-brifing/collector/publish.sh >> /var/log/kripto-brifing.log 2>&1
15 2 * * 0 /bin/bash /opt/kripto-brifing/collector/weekly_backtest.sh >> /var/log/kripto-brifing-backtest.log 2>&1
```

Cron satırı **terminale yazılmaz**: ya `crontab -e` ile dosyaya eklenir ya da `(crontab -l; echo '...') | crontab -` ile. İkinci yöntemde komut tek kez çalıştırılmalı, yoksa satır çift eklenir.

### Sık kullanılan komutlar

```bash
# Kod güncellemesi (sadece collector/ altı değiştiyse gerekir)
cd /opt/kripto-brifing && git pull origin claude/elegant-cori-lln6rd && git log --oneline -1

# Testler
python3 -m unittest discover -s collector/tests

# Elle veri topla + yayınla
bash /opt/kripto-brifing/collector/publish.sh

# Sadece ekrana bas (yayınlamaz)
python3 /opt/kripto-brifing/collector/binance_collector.py

# Backtest'i elle çalıştır (~15-30 sn) ve sonuçları yayınla
python3 collector/backtest.py > /dev/null && sed -n '/^3)/,/^$/p' collector/data/backtest_report.txt
bash collector/publish.sh | tail -2

# Geçmiş veriyi güncelle (haftalık cron zaten yapar)
python3 collector/history_download.py

# Loglar
tail -20 /var/log/kripto-brifing.log
tail -40 /var/log/kripto-brifing-backtest.log
```

`briefing/routine_prompt.txt` ve bu dosyadaki değişiklikler sunucuda `git pull` **gerektirmez**.

---

## 9. Claude Routine

- Ad: **Kripton Karar Sabah Brifingi**
- ID: `trig_01Swxrg8zfpKMCuTfTBUAMJU`
- Düzenleme: https://claude.ai/code/routines/trig_01Swxrg8zfpKMCuTfTBUAMJU
- Zamanlama: `47 5 * * *` (UTC) = **her gün 08:47 TSİ**
- Bağlayıcı: Crypto.com (fiyatlar)
- Telegram gönderimi routine ortamındaki `TELEGRAM_BOT_TOKEN` ve `TELEGRAM_CHAT_ID` değişkenleriyle yapılır.
- ⚠️ Routine `http_api` ile oluşturulduğu için **Claude bu routine'i güncelleyemez.** Prompt değişikliklerini Okan elle yapıştırır. Claude'un görevi `briefing/routine_prompt.txt` dosyasını güncelleyip push etmek ve **tam metni** sohbete yazmak.

### Veri kaynakları

| Veri | Kaynak |
|---|---|
| Fiyat, 24s değişim, high/low | Crypto.com bağlayıcısı (BNB hariç; BNB Binance verisinden) |
| Funding, OI, long/short, trend, ATR, seviyeler, yüzdelikler | `market-data/latest.json` |
| Yön özeti, kanıt, SL notu | `latest.json` → `direction_summary`, `evidence` |
| Korku-açgözlülük | `api.alternative.me/fng/?limit=2` |
| Haber, makro takvim | Web araması (saat bulunamazsa standart ABD yayın saatleri) |

### Brifing yapısı (11 madde)

1. Piyasa (BTC/ETH, gün içi konum, trend) · 2. Düşen/yükselen · 3. Korku-açgözlülük · 4. Türev radarı (yüzdeliklerle) · 5. Haberler · 6. Takvim · 7. Liq radarı (ATR cinsinden) · 8. Kurallarına uygunluk 🟢🟡🔴 · 9. Kritik seviyeler (dünün / 7 günün tepe-dibi) · 10. **Yön özeti** 📈📉⚪ · 11. ⚠️ Bugün dikkat

### Routine prompt'u (güncel, birebir — `briefing/routine_prompt.txt` ile aynı)

Son değişiklik (commit `762762f`): 10. maddede USDT değerleri 2 ondalıklı, 9. maddede en yakın seviye kuralı. Okan'a tam metin verildi; routine'e yapıştırıldığı henüz teyit edilmedi.

```
Okan için kripto sabah brifingi hazırla ve Telegram kanalına gönder. Al/sat tavsiyesi verme.

OKAN'IN PROFİLİ VE KURALLARI
- 3 yıllık kripto tecrübesi, hedef aktif işlemle düzenli gelir. Kasa ~500 USDT.
- Sadece futures, her işlem 5x isolated, işlem başı 50 USDT marj, en fazla 5 pozisyon, gün içi ile 3-4 gün arası tutar.
- TP: %10 ROE (≈%2 fiyat). SL koymuyor, liq'e yakın bir kez ekleme yapıyor.
- Risk/ödül: kazanç ≈ +5 USDT, liq ≈ -50 USDT (eklemeyle -100). Başa baş için ~%91 isabet gerekir. 5x'te ~%20 ters hareket = liq.
- Sadece büyük, stabil coinler. Memecoin ve volatil coin yok. 5x üstü kaldıraç yok.
HATA MÜZESİ
- En pahalı ders: memecoin'de kasa bir gecede 2 katına çıktı, kâr alınmadı, liq oldu, "dipten döner, kaybımı kurtarırım" diyerek tekrar girdi, 2-3 liq sonrası kasa sıfırlandı.
- Tekrarlayan hatalar: zarardaki pozisyona ekleme, FOMO, kâr alamamak, başkasının sözüyle işlem, plansız pozisyon, liq sonrası intikam işlemi.
- Uyarı cümleleri: "dipten döner", "kaybımı kurtarırım", "bu garanti işlem", "bu sefer farklı", "herkes alıyor".

VERİ
- Tarih/saat: `TZ=Europe/Istanbul date` komutuyla al. "Bugün/yarın" ifadelerini buna göre yaz.
- Coin listesi (11 coin): BTC, ETH, BNB, SOL, XRP, ADA, AVAX, LINK, LTC, BCH, SUI.
- Fiyatlar: Crypto.com bağlayıcısı (BNB hariç 10 coin; USDT pariteleri; son fiyat, 24s değişim, 24s high/low). BNB Crypto.com'da olmadığı için BNB'nin fiyat, 24s değişim ve high/low değerlerini Binance verisinden (price, change_24h_pct, high_24h, low_24h) al.
- Binance futures türev verisi: SADECE şu komutla al: curl -s "https://raw.githubusercontent.com/doruq-IT/kripto-brifing/market-data/latest.json" → her coin için funding_rate_pct (funding_interval_h saatlik funding, yüzde), oi_usdt, oi_change_4h_pct, oi_change_24h_pct, global_long_pct (long hesap yüzdesi), top_trader_position_ls_ratio, taker_buy_sell_ratio (1'in altı = satıcı baskın), range_24h_pct. Ek alanlar: dist_ema50_1d_pct ve dist_ema200_1d_pct (fiyatın günlük EMA50/EMA200'e uzaklığı, + = üstünde), trend_4h (yukarı/aşağı), atr_pct_1d (ATR = ortalama günlük hareket, %), liq_distance_in_atr (5x liq mesafesi kaç günlük ortalama hareket ediyor), prev_day_high/prev_day_low (dünün tepe/dibi), high_7d/low_7d (son 7 günün tepe/dibi), funding_pctl_30d, global_long_pct_pctl_30d ve top_trader_ratio_pctl_30d (değerin coinin kendi son 30 günündeki yüzdelik sırası: 90 = son 30 günün en yüksek %10'u), oi_change_7d_pct, btc_trend_up_1d, conditions_true, evidence_hits ve üst düzeyde evidence (haftalık backtest sonucu) ile direction_summary (coin bazında yön özeti). Ek alanlardan biri yoksa veya null ise o bilgiyi yazma, tahmin etme; 7. maddede 24s aralığın 5x liq mesafesine (~%20) oranını, 9. maddede 24s high/low seviyelerini kullan. Bu veri Okan'ın VPS'inden saatlik yayınlanıyor. generated_at alanı 3 saatten eskiyse, dosya alınamazsa veya coins boşsa türev maddesine "Binance verisi alınamadı" yaz ve bu verideki hiçbir rakamı kullanma. Fiyat için ana kaynak Crypto.com olarak kalsın; Crypto.com fiyatı alınamazsa bu dosyadaki price/high_24h/low_24h yedek olarak kullanılabilir. Dosyada olmayan, errors alanında geçen veya ilgili alanı null olan coin için o rakamı "veri yok" yaz, tahmin etme; bu coini 8. maddede gruplama, maddenin sonuna "Veri yok: <coinler>" diye ekle.
- Korku-açgözlülük endeksi: SADECE şu komutla al: curl -s "https://api.alternative.me/fng/?limit=2" → bugünkü değer, sınıfı ve dünkü değer. Başka site kullanma.
- Haberler ve makro takvim: web araması. Tek kaynağa dayanan haberi, iddiayı veya rakamı her seferinde "doğrulanmadı" diye işaretle. Rakam uydurma; bulamadığını "alınamadı" yaz.

DİL (en önemli kural)
- Okan mesajı telefonda, sabah hızlıca okuyacak. Her maddeyi ilk okuyuşta anlaşılacak kadar basit ve net yaz.
- Kısa cümleler kur. Bir cümlede tek fikir olsun.
- Teknik terim kullanırsan yanına kısa Türkçe karşılığını yaz: OI = açık pozisyon miktarı, funding = long/short arasındaki periyodik ödeme, liq = likidasyon, ATR = ortalama günlük hareket, EMA = üssel hareketli ortalama.
- 4., 7., 8., 9. ve 11. maddelerde rakamı verdikten sonra "→" ile tek cümlelik "bu ne demek" açıklaması ekle. Örn: "BCH: açık pozisyon 24 saatte -%19,6 → çok sayıda pozisyon kapanmış ya da likide olmuş olabilir."
- Belirsiz ifade kullanma: "risk artabilir" deme; kimin için (long mu short mu tutan) ve hangi risk (likidasyon, yeni dip, sert düşüş, sert yükseliş) olduğunu yaz.
- Türev verisinden çıkarımları "olabilir", "olası" gibi temkinli dille yaz; kesin hüküm kurma.

FORMAT (düz metin, en fazla 11 madde, her madde en fazla 3 satır (10. madde en fazla 6 satır), toplam 3800 karakteri geçme)
- Hiç link, URL, köşeli parantez veya Markdown kullanma. Kaynakları sadece adıyla yaz.
- Yüzdeleri Türkçe biçimde yaz: -%2,19 / +%0,24. Pozitif değerlerde + işaretini yaz; bu kural funding ve OI değişimi dahil tüm yüzdeler için geçerli (örn: funding +%0,0061).
- Maddeleri "1.", "2." biçiminde numarala ve her maddeye kısa bir başlık koy (örn: "4. Türev radarı:").
- 8., 9. ve 10. maddeler işlem önerisi değildir: "al", "sat", "gir", "long aç", "short aç" gibi ifadeler, giriş seviyesi veya hedef fiyat yazma. 🟢 işareti "işlem aç" anlamına gelmez, sadece bugünkü verinin Okan'ın kurallarıyla çelişmediğini gösterir.
Başlık: "☀️ Sabah Brifingi — GG.AA.YYYY HH:MM TSİ"
1. Piyasa: BTC ve ETH fiyatı, 24s değişim, gün aralığındaki konum ((fiyat-low)/(high-low)): %0-25 "günün dibine yakın", %25-75 "günün ortasında", %75-100 "günün tepesine yakın". Ardından tek kısa ifadeyle trend: günlük EMA50'nin üstünde/altında ve 4 saatlik trend yukarı/aşağı (dist_ema50_1d_pct, trend_4h).
2. Düşen/yükselen: en çok düşen ve yükselen 3'er büyük coin (tek satır)
3. Piyasa havası: korku-açgözlülük bugünkü değer + sınıf, dünkü değer (Alternative.me). Sınıfı Türkçe yaz: Aşırı Korku, Korku, Nötr, Açgözlülük, Aşırı Açgözlülük
4. Türev radarı (Binance): BTC ve ETH için funding, 24s açık pozisyon (OI) değişimi, long hesap yüzdesi; funding ve long yüzdesinin yanına 30 günlük yüzdelik sırasını yaz (örn: "funding +%0,0061, son 30 günün ortası"). Yüzdelik 90 ve üstü "son 30 günün en yükseklerinde", 10 ve altı "son 30 günün en düşüklerinde" demektir. Ayrıca listeden en uç sinyali veren 1-2 coin (funding veya long yüzdesi yüzdeliği ≥90 ya da ≤10, en büyük 24s OI değişimi veya long hesap oranı %70 üstü). Anlamlandırma: OI artışı = yeni pozisyon birikiyor; fiyat düşerken sert OI düşüşü = pozisyonlar kapanmış ya da likide olmuş olabilir; long hesap %70 üstü = kalabalık long, ters harekette toplu likidasyon riski.
5. Haberler: en fazla 2 önemli haber, her biri tek cümle. Tek kaynaklı iddia ve rakamları "doğrulanmadı" diye işaretle
6. Takvim: bugün ve yarın önemli makro veriler, gün adı ve TSİ saatiyle. Saat bulunamazsa standart saatleri kullan ve yanına "(standart saat)" yaz: ABD verileri (CPI, PCE, istihdam, GSYH, perakende satışlar, haftalık işsizlik başvuruları) 08:30 ABD Doğu saati = ABD yaz saati döneminde (Mart'ın 2. pazarı – Kasım'ın 1. pazarı) 15:30 TSİ, diğer dönemde 16:30 TSİ; FOMC faiz kararı 14:00 ABD Doğu saati = 21:00 / 22:00 TSİ.
7. Liq radarı: liq_distance_in_atr en düşük 3 coin; her biri için 24s aralık ve liq mesafesinin kaç günlük ortalama hareket (ATR) ettiği. Örn: "SUI günde %14,5 oynadı, ATR %7,8 → liq mesafen yaklaşık 2,5 günlük ortalama hareket kadar"
8. Kurallarına uygunluk: listedeki 11 coini Binance verisine göre üç gruba ayır, her grupta coin adı ve belirleyici rakam, sonra "→" ile tek cümle açıklama:
   🟢 Kurallarınla çelişmiyor: 24s aralık ≤ %5 (liq mesafenin ≤ %25'i) VE long hesap oranı < %70 VE |OI 24s değişimi| < %10
   🔴 Bugün kurallarına uymuyor: 24s aralık ≥ %10 (liq mesafenin ≥ yarısı) VEYA |OI 24s değişimi| ≥ %15 VEYA 24s fiyat değişimi ≤ -%5
   🟡 Temkinli: geri kalanlar (en belirleyici nedeni yaz: kalabalık long, geniş aralık veya OI hareketi)
   Binance verisi alınamadıysa bu maddeye "Binance verisi olmadan filtre uygulanamadı" yaz.
9. Kritik seviyeler: en fazla 2 tane, BTC/ETH veya 4. maddede öne çıkan coin için dünün tepe/dibi (prev_day_high/low) veya son 7 günün tepe/dibi (high_7d/low_7d) seviyesine dayalı. Aşağı yön için fiyatın altındaki en yakın seviyeyi seç: dünün dibi fiyatın altındaysa onu, değilse son 7 günün dibini kullan. Yukarı yön için de aynısı: dünün tepesi fiyatın üstündeyse onu, değilse son 7 günün tepesini kullan. Biçim: "<coin> <seviye> altına inerse (dünün dibi) → long tutanlar için likidasyon zinciri riski artabilir" veya "<coin> <seviye> üstüne çıkarsa (7 günün tepesi) → short tutanlar için sert yükseliş riski artabilir". Seviyenin ne olduğunu (dünün/7 günün dibi/tepesi) ve kimin için hangi risk olduğunu mutlaka yaz. Yön tahmini veya işlem önerisi yapma.
10. Yön özeti (geçmiş veriye göre; işlem önerisi değil): SADECE direction_summary ve evidence alanlarını kullan, kendi yorumunla yön üretme. Bu madde en fazla 6 satır olabilir.
   - direction_summary null ise veya evidence.status "ok" değilse sadece "Yön özeti: backtest verisi yok." yaz.
   - Aksi halde şu satırları bu sırayla yaz. Aynı koşulu paylaşan coinleri tek satırda grupla; koşulu sade Türkçe ve kısa yaz (desc_tr'nin anlamını değiştirme); USDT değerlerini işaretli, 2 ondalıklı ve Türkçe ondalıkla yaz (örn: +2,75; +0,01; -1,48), liq oranını 1 ondalıkla yaz (örn: %0,4):
     "📈 Long lehine: <coinler> → <koşul>, geçmişte long işlem başı <avg_pnl_true> USDT (diğer günler <avg_pnl_false>, liq %<liq_rate_true>)" — long_favored boşsa "📈 Long lehine: kanıt yok"
     "📉 Short lehine: <coinler> → <koşul>, geçmişte short işlem başı <avg_pnl_true> USDT (diğer günler <avg_pnl_false>, liq %<liq_rate_true>)" — short_favored boşsa "📉 Short lehine: kanıt yok"
     long_weaker veya short_weaker doluysa: "⚠️ <Long/Short> için zayıf: <coinler> → <koşul>, <avg_pnl_true> USDT"
     "⚪ Belirgin üstünlük yok: <no_evidence coinleri>"
     "Filtresiz ortalama: long <evidence.base.long.avg_pnl_usdt>, short <evidence.base.short.avg_pnl_usdt> USDT/işlem (son <evidence.period.days> gün, 11 coin; geleceği garanti etmez)."
   - Stop notu: evidence.sl_summary içindeki kayıtlardan significant alanı true olan varsa tek satır ekle: "Stop verisi: <yön ya da koşul> için %<best_sl_pct> stop ortalamayı <none_avg_pnl> → <best_avg_pnl> USDT yaptı." significant true olan yoksa stop hakkında hiçbir şey yazma.
   - "Lehine" kelimesini kullan; "gir", "al", "sat", "long aç", "short aç" yazma. Rakamları değiştirme.
11. ⚠️ Bugün dikkat: kurallar ve hata müzesine göre tek ana uyarı, en az bir somut sayıyla (4., 7., 8. veya 10. maddeden ya da makro saatinden). Kalabalık long + yükselen OI varsa bunu "herkes alıyor"/FOMO hatasıyla ilişkilendirebilirsin. Sert OI düşüşü olan coinlerde "dipten döner" diyip zarardaki pozisyona ekleme riskini hatırlat. Her gün aynı cümleyi kurma. Sade dille, en fazla 3 satır.
Numarasız satır: "Bugün hangi coinleri izliyorsun?"
Son satır: "Kaynaklar:" ve kaynak adları, virgülle ayrılmış (sadece yayın/site adı; Binance verisi kullanıldıysa "Binance Futures" ekle). Kaynak adlarına saat, sayı, tarih veya başka metin ekleme.

GÖNDERİM
Metni /tmp/brifing.txt dosyasına yaz. Göndermeden önce Markdown linklerini temizle:
sed -i -E 's/\[([^]]+)\]\([^)]+\)/\1/g; s#https?://[^ )]+##g' /tmp/brifing.txt
Karakter sayısını `wc -m /tmp/brifing.txt` ile kontrol et; 3800'ü geçiyorsa önce 5. ve 6. maddeleri, sonra 2., 1. ve 4. maddeyi kısaltıp tekrar yaz; 10. maddedeki rakamları kısaltma.
Göndermeden önce metni bir kez oku: her madde tek okuyuşta anlaşılıyor mu, "risk artabilir" gibi kimin için olduğu belirsiz bir ifade kaldı mı, son satırda kaynak adları dışında metin var mı? Varsa düzelt.
Sonra gönder (token'ı asla yazdırma):
curl -sS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" --data-urlencode "text@/tmp/brifing.txt" -d "disable_web_page_preview=true" -w "\nHTTP %{http_code}\n"
HTTP 200 ve "ok":true değilse hatayı raporla. Başarılıysa tek cümleyle "gönderildi" yaz.
```

---

## 10. Okan'ın profili (brifingin dayandığı kurallar)

- Kasa ~500 USDT; sadece futures, 5x isolated, işlem başı 50 USDT marj, en fazla 5 pozisyon, gün içi ile 3-4 gün arası tutar.
- TP %10 ROE (≈%2 fiyat). SL yok (28.09 backtest'inden sonra da bilinçli olarak bu karar verildi). Liq'e yakın bir kez ekleme yapıyor. 5x'te ~%20 ters hareket = liq.
- Başa baş için ~%91 isabet gerekiyor (kazanç ≈ +5 USDT, kayıp ≈ −50 / −100 USDT). Backtest bu yapısal riski veriyle doğruladı: filtresiz long'da gereken TP oranı %76,9, gerçekleşen %68.
- Sadece büyük ve stabil coinler; memecoin ve volatil coin yok.
- Brifing **al/sat tavsiyesi vermez.** 8. madde (filtre), 9. madde (seviyeler) ve 10. madde (yön özeti) sadece kurallara uygunluğu, risk seviyelerini ve geçmiş veriyi gösterir.

---

## 11. Alınan kararlar ve gerekçeleri

| Karar | Gerekçe |
|---|---|
| Proxy/Cloudflare ile Binance'e erişim **yok** | Konum kontrolünü atlatmak Binance şartlarına aykırı; Cloudflare IP'leri de sık engelleniyor |
| Veri VPS'te toplanır, GitHub'a yayınlanır | Okan'ın sunucusu uygun bölgede; brifing sadece hazır veriyi okur |
| `market-data` tek commit, force-push | Repo geçmişi şişmesin |
| Sadece Python stdlib | Sunucuda ek kurulum gerekmesin |
| DOT çıkarıldı, BNB eklendi | DOT OI ~38M$ (en sığ, iğne riski); BNB ilk 5'te, OI ~441M$, düşük oynaklık |
| TRX, HYPE, DOGE, ZEC eklenmedi | TRX: %2 TP için yavaş olabilir (opsiyonel). Diğerleri yeni, volatil veya memecoin |
| Prompt'ta "DİL" bölümü ve "→ bu ne demek" | Brifing ilk okuyuşta anlaşılsın |
| Kanıt sadece backtest'te doğrulanmış koşullardan | "Veri varsa göster, yoksa yok de"; yorumla kanıt üretilmez |
| Canlı ve backtest aynı `features.py` | Brifingte aktif görünen koşul, test edilen koşulla birebir aynı tanımda olsun |
| Doğrulama ölçütü PnL (temiz kazanç değil) | Oynaklık iki yönde de TP'yi hızlandırıyor ama liq'i artırıyor; temiz oran yanıltıcı |
| Sıkı eşik: %99,8 + iki yarı + min n | 58 test aynı anda; tesadüfi "kanıt"ı elemek için |
| Funding 8 saate normalize | Bazı coinlerde funding 4 saatte bir; ham oranlar karşılaştırılamaz |
| 8. madde filtresi değiştirilmedi | Hiçbir eşik değişikliği doğrulanmadı; %70 kuralı yönsel olarak destekleniyor, yüzdelik alternatifi desteklenmiyor |
| 10. madde "yön özeti", gruplama toplayıcıda | Okan tek bakışta görsün; model gruplama yapmasın, sadece yazsın |
| "Lehine" dili | Yön bilgisi net, ama işlem emri değil |
| SL yok (şimdilik) | Doğrulanmış short durumlarında sıkı stop kazancı yok ediyor; genelde anlamlı iyileşme yok |
| Makro saatlerde standart saat yedeği | Saat bulunamadığında 08:30 ET = 15:30/16:30 TSİ, "(standart saat)" etiketiyle |
| Deribit / ETF akışı / token unlock şimdilik yok (Faz 2) | Backtest'e uygun geçmiş arşivleri yok veya ücretli; kanıt üretemez |
| Tasfiye (liquidation) akışı yok | Binance REST ucu kaldırıldı; websocket dinleyici gerekir, geçmişi yok |
| Güvenlik ayrıntıları repoda yok | Repo herkese açık |

---

## 12. Doğrulanmış durum (28.09.2026)

- ✅ VPS'ten Binance erişimi (fapi + spot) çalışıyor; VPS `claude/elegant-cori-lln6rd` branch'inde, sunucuda 22 test OK
- ✅ Saatlik yayın çalışıyor: 11 coinde tüm alanlar dolu, `errors: {}`, `conditions_unknown` boş
- ✅ Geçmiş veri tam (eksik gün yok); ilk backtest ve SL karşılaştırması yayında
- ✅ `evidence.status = ok`, 2 doğrulanmış koşul; `direction_summary` doğru (28.09 akşamı short lehine: BCH, SUI, ADA, AVAX; long lehine yok)
- ✅ Haftalık backtest cron'u kurulu (pazar 02:15 UTC); ilk otomatik çalışma 04.10.2026
- ✅ Routine elle iki kez çalıştırıldı (22:05 ve 22:21 TSİ): Binance kaynaklı rakamların hepsi veriyle birebir, gruplar doğru, 3.800 karakter sınırının altında
- ⏳ `762762f` prompt'unun routine'e yapıştırıldığının teyidi
- ⏳ İlk otomatik brifing (yeni sistemle): 29.09.2026 08:47 TSİ

---

## 13. Sıradaki adımlar / açık konular

1. **29.09 sabahı otomatik brifingi kontrol et.** 9. madde en yakın seviyeyi seçmiş mi, 10. madde 2 ondalıklı mı, tüm rakamlar `latest.json` ile tutuyor mu?
2. **04.10 (pazar) ilk otomatik backtest'ten sonra** raporu oku. Doğrulanan koşullar kalıcı mı, yeni koşul çıktı mı, SL sonucu değişti mi?
3. **Bir hafta izle, küçük düzeltmeleri biriktir,** sonra prompt'u toplu güncelle.
4. 8. madde filtresi: her hafta raporla birlikte yeniden bak (🟢 long ve %70 kuralı anlamlılığa yakın).
5. Bilinen küçük pürüzler:
   - Makro takvimde tarih/saat kaynakları bazen çelişiyor (brifing bunu yazıyor).
   - Crypto.com ve Binance 24 saatlik değişimleri farklı borsalar olduğu için biraz farklı olabilir (normal).
6. Faz 2 (opsiyonel, sadece açıklayıcı): Deribit DVOL/skew (BTC/ETH), spot ETF akışları, token unlock takvimi, makro (DXY/10Y).
7. Opsiyonel: TRX'i eklemek; backtest süresini 2 yıla çıkarmak (`DAYS=730`) ve farklı piyasa rejimlerinde test etmek; eklemeli kurguyu (liq'e yakın ekleme) simüle etmek; kod branch'ini main'e merge etmek.
8. Sunucu güvenliği bu projenin kapsamı dışında; Okan'a ayrıca hatırlatıldı. Ayrıntılar repoya yazılmaz.

---

## 14. Sorun giderme

| Belirti | Olası neden / çözüm |
|---|---|
| Brifingte "Binance verisi alınamadı" | `generated_at` 3 saatten eski. VPS'te `tail /var/log/kripto-brifing.log`; `bash collector/publish.sh` ile elle dene |
| 10. madde "backtest verisi yok" | `evidence.status` ok değil. Backtest 14 günden eski olabilir → `tail -40 /var/log/kripto-brifing-backtest.log`, gerekirse `bash collector/weekly_backtest.sh` |
| Toplayıcıda `UYARI: klines/funding/spot` | Opsiyonel uç geçici olarak başarısız; temel veri yine yayınlanır. Sürerse Binance erişimini kontrol et |
| `history_download.py`: "metrics başlığı beklenenden farklı" | data.binance.vision CSV formatı değişmiş; çıktıyı Claude'a ver, parser güncellenir |
| `publish.sh` push hatası | Deploy key veya GitHub erişimi; `ssh -i ~/.ssh/kripto_brifing_deploy -T git@github.com` |
| `backtest.py \| head` sonrası `BrokenPipeError` | Zararsız; `head` çıktıyı kestiği için. Dosyalar önceden yazılır |
| Cron çalışmıyor | `crontab -l \| grep kripto` iki satır göstermeli |

---

## 15. Yeni oturumda nasıl devam edilir

Yeni Claude oturumunda (repo `doruq-IT/kripto-brifing`, branch `claude/elegant-cori-lln6rd`) şunu yaz:

> `PROJE_DURUMU.md` dosyasını oku. Kripto brifing projesine kaldığımız yerden devam edeceğiz. [yapmak istediğin şey]

Çalışma kuralları (oturmuş düzen):
- Claude VPS'e bağlanamaz. Sunucuda çalıştırılacak komutları yazar, Okan çalıştırıp çıktıyı yapıştırır.
- Claude Binance'e erişemez; ama `market-data` branch'indeki `latest.json`, `backtest_report.txt` ve `backtest_summary.json` dosyalarını okuyabilir. Doğrulamayı bunlarla yapar.
- Claude routine'i güncelleyemez. `briefing/routine_prompt.txt` dosyasını güncelleyip push eder ve **tam metni** sohbete yazar, Okan yapıştırır. Bu dosyadaki prompt kopyası da senkron tutulur.
- Sunucuda `git pull origin claude/elegant-cori-lln6rd` sadece `collector/` altı değiştiğinde gerekir; Claude bunu ayrıca söyler.
- Adım adım ilerlenir; her adımdan sonra çıktı kontrol edilir.
- Kod değişikliği push edilmeden önce testler çalıştırılır; yeni davranış için test eklenir.
- İddialar veriyle desteklenir; doğrulanmamış sonuç "kanıt" olarak sunulmaz, yoksa "yok" denir.
- Brifing hiçbir koşulda al/sat tavsiyesi, giriş seviyesi veya hedef fiyat vermez.
