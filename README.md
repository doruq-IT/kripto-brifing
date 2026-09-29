# kripto-brifing

## Mimari

```
VPS (okan-vps, cron saatlik)                GitHub                      Claude sabah brifingi (08:47 TSİ)
binance_collector.py -> latest.json  --push--> market-data branch  <--curl--  raw.githubusercontent.com/.../latest.json
state_engine.py -> notify.py --------------------------------------------> Telegram (saatlik risk durumu)
```

Brifing bulutta çalıştığı için Binance'e doğrudan erişemiyor (HTTP 451). Veriyi VPS toplar, `market-data` branch'ine tek commit olarak yayınlar, brifing oradan okur.

## collector/binance_collector.py

Herkese açık Binance USDT-M Futures endpoint'lerini kullanır. API anahtarı gerektirmez, sadece Python standart kütüphanesiyle çalışır. Varsayılan semboller: BTC, ETH, BNB, SOL, XRP, ADA, AVAX, LINK, LTC, BCH, SUI (USDT).

| Alan | Endpoint |
|---|---|
| Fiyat, 24s değişim, high/low, hacim | `/fapi/v1/ticker/24hr` |
| Mark fiyat, funding, sonraki funding saati | `/fapi/v1/premiumIndex` |
| Open interest (USDT) + 4s/24s değişim | `/futures/data/openInterestHist` |
| Global long/short hesap oranı | `/futures/data/globalLongShortAccountRatio` |
| Top trader long/short pozisyon oranı | `/futures/data/topLongShortPositionRatio` |
| Taker alış/satış oranı | `/futures/data/takerlongshortRatio` |
| 1s/1g mum → EMA20/50/200, ATR, 4s trend, dün/7 gün tepe-dip, 24s taker oranı | `/fapi/v1/klines` |
| Spot 1s mum → spot/vadeli alım baskısı karşılaştırması | `/api/v3/klines` (api.binance.com) |
| Funding geçmişi → 30 günlük yüzdelik, funding aralığı (4s/8s) | `/fapi/v1/fundingRate` |
| Prim endeksi 1s → prim %, 7 günlük z-skoru; anlık basis (mark/index) | `/fapi/v1/premiumIndexKlines`, `/fapi/v1/premiumIndex` |

Ortam değişkenleri: `SYMBOLS` (virgülle ayrılmış), `PERIOD` (taker oranı için, varsayılan `4h`), `DATA_DIR`.

Özellik ve koşul tanımları `collector/features.py`'dedir; canlı toplayıcı ve backtest aynı kodu kullanır.

## Backtest (kanıt motoru)

Brifingin "veri ne diyor" maddesi sadece geçmiş veride doğrulanmış koşullara dayanır.

- `collector/history_download.py`: geçmiş veriyi indirir → `collector/data/history/`
  - Futures/spot 1s mum ve funding: Binance API (canlıyla aynı uçlar)
  - OI, global long/short, top trader oranı: `data.binance.vision` günlük *metrics* arşivi (API sadece son 30 günü verir)
- `collector/backtest.py`: son 2 yılda (`DAYS=730`) her coin için 4 saatte bir (`STEP_H=4`; 01, 05, … 21 UTC)
  koşulları hesaplar, bir sonraki saatin açılışında long ve short sanal işlem açar
  (TP +%2, SL yok, liq -%19,5, en fazla 96 saat, ücret ve funding dahil). Doğrulama ölçütü işlem başı
  ortalama PnL farkı ("temiz kazanç" oranı sadece bilgi). Her koşul için fark, haftalık blok bootstrap ile
  Bonferroni düzeltmeli güven aralığı (100 − 5/test sayısı; 76 testte %99,93) ve dönemin iki yarısında tutarlılık kontrolü.
  %95 aralığı geçenler ayrıca "zayıf işaret" olarak raporlanır (kanıt değildir). Çıktı: `data/backtest_summary.json`, `data/backtest_report.txt`.
- `collector/weekly_backtest.sh`: ikisini sırayla çalıştırır (haftalık cron). Sonuçlar bir sonraki saatlik yayında
  `latest.json` → `evidence` alanına ve `market-data` branch'ine (`backtest_report.txt`) girer.

Rapor ayrıca stop-loss karşılaştırması içerir: aynı işlemler stop'suz ve `SL_GRID` seviyelerinde (varsayılan %2,3,5,8,10 fiyat) simüle edilir; fark eşleştirilmiş haftalık bootstrap ile test edilir.

Ortam değişkenleri: `DAYS` (varsayılan 730), `STEP_H` (4), `CI_LEVEL`, `TP_PCT`, `ADV_PCT`, `LIQ_PCT`, `HOLD_H`, `MARGIN`, `LEV`, `FEE_PCT`, `BOOT`, `MIN_N`, `SL_GRID`, `SL_SLIP`.

## Saatlik risk durumu (collector/state_engine.py)

`publish.sh` her saat toplayıcıdan sonra çalıştırır. Her coin için sabah brifingi 8. madde ile aynı kurallarla
🟢/🟡/🔴 seviyesi hesaplar (yön sinyali değildir), `data/state.json`'daki önceki durumla karşılaştırır.
Kötüleşme hemen, iyileşme 2 saat teyitle kabul edilir. Değişiklik varsa detaylı mesaj; yoksa 08–24 TSİ tek satır özet,
00–08 TSİ mesaj yok. Gönderim `notify.py` ile; kimlik bilgileri repo dışında `/etc/kripto-brifing.env`
(`KRIPTO_TG_TOKEN`, `KRIPTO_TG_CHAT`, izin 600). Dosya yoksa veya `DRY_RUN=1` ise mesaj sadece log'a basılır.

Testler: `python3 -m unittest discover -s collector/tests -v`

## VPS kurulumu

1. Kodu güncelle:
   ```bash
   cd /opt/kripto-brifing && git pull
   python3 collector/binance_collector.py
   ```
2. Yayın için deploy key oluştur:
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/kripto_brifing_deploy -N "" -C "okan-vps kripto-brifing"
   cat ~/.ssh/kripto_brifing_deploy.pub
   ```
   Çıktıyı GitHub'da repo → Settings → Deploy keys → Add deploy key alanına ekle, **Allow write access** kutusunu işaretle.
3. Elle test:
   ```bash
   bash /opt/kripto-brifing/collector/publish.sh
   ```
4. Cron (`crontab -e` ile dosyaya eklenir, terminale yazılmaz):
   ```
   30 * * * * /bin/bash /opt/kripto-brifing/collector/publish.sh >> /var/log/kripto-brifing.log 2>&1
   ```
5. Haftalık backtest cron'u (pazar 02:15 UTC):
   ```
   15 2 * * 0 /bin/bash /opt/kripto-brifing/collector/weekly_backtest.sh >> /var/log/kripto-brifing-backtest.log 2>&1
   ```
6. Saatlik risk durumu için Telegram kimlik bilgileri (`nano` ile, komut satırına yazmadan):
   ```bash
   nano /etc/kripto-brifing.env   # KRIPTO_TG_TOKEN=... ve KRIPTO_TG_CHAT=... satırları
   chmod 600 /etc/kripto-brifing.env
   ```
