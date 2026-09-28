# kripto-brifing

## collector/binance_collector.py

Binance USDT-M Futures'tan herkese açık piyasa verisini toplar. API anahtarı gerektirmez, sadece Python standart kütüphanesini kullanır.

Her sembol için alınanlar:

| Veri | Endpoint |
|---|---|
| Mark / index fiyat, funding rate | `/fapi/v1/premiumIndex` |
| Open interest (adet ve USDT) | `/fapi/v1/openInterest` |
| Global long/short hesap oranı | `/futures/data/globalLongShortAccountRatio` |

Çıktılar `collector/data/` altına yazılır:
- `latest.json`: son snapshot
- `snapshots.jsonl`: tüm geçmiş, her satırda bir sembol

### VPS kurulumu

Trading bot container'ından bağımsız çalışır. Bot koduna ve `.env` dosyasına dokunmaz.

```bash
cd /opt
git clone https://github.com/doruq-IT/kripto-brifing.git
cd kripto-brifing
git checkout claude/binance-api-connection-test-4omj2z
python3 collector/binance_collector.py BTCUSDT ETHUSDT   # elle test
```

Cron ile 4 saatte bir çalıştırmak için (`crontab -e`):

```
5 */4 * * * SYMBOLS=BTCUSDT,ETHUSDT PERIOD=4h /usr/bin/python3 /opt/kripto-brifing/collector/binance_collector.py >> /var/log/kripto-brifing.log 2>&1
```

Ortam değişkenleri: `SYMBOLS` (virgülle ayrılmış), `PERIOD` (varsayılan `4h`), `DATA_DIR`.
