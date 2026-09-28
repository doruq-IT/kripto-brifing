# kripto-brifing

## Mimari

```
VPS (okan-vps, cron saatlik)                GitHub                      Claude sabah brifingi (08:47 TSİ)
binance_collector.py -> latest.json  --push--> market-data branch  <--curl--  raw.githubusercontent.com/.../latest.json
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

Ortam değişkenleri: `SYMBOLS` (virgülle ayrılmış), `PERIOD` (oranlar için, varsayılan `4h`), `DATA_DIR`.

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
