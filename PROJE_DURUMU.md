# Kripto Brifing — Proje Durumu ve Devam Rehberi

> Son güncelleme: 28.09.2026, 17:30 TSİ civarı
> Bu dosya, projeye yeni bir Claude oturumunda kaldığı yerden devam etmek için hazırlandı. Yeni oturumda bu dosyayı ver ve "buradan devam edelim" de.

> ⚠️ Bu repo **herkese açık** (GitHub'dan şifresiz clone edilebiliyor). Bu dosyaya ve repoya IP adresi, SSH portu, token, chat ID, API anahtarı, sunucudaki diğer servislerin ayrıntıları veya güvenlik açıkları **yazılmamalı**.

---

## 1. Projenin amacı

Okan'ın her sabah Telegram'a gelen **"Kripton Karar Sabah Brifingi"** mesajına Binance Futures türev verilerini (funding, açık pozisyon, long/short oranları) eklemek ve brifingi Okan'ın işlem kurallarına göre sade bir dille yazdırmak.

**Temel sorun:** Brifing Claude'un bulut ortamında çalışıyor ve Binance bu ortamdan erişimi engelliyor (**HTTP 451**, "restricted location"). Proxy veya Cloudflare ile bu engeli atlatmak **bilerek tercih edilmedi** (Binance kullanım şartlarına aykırı, ayrıca güvenilmez).

**Çözüm:** Veriyi Okan'ın kendi VPS'i toplar, GitHub'a yayınlar, brifing oradan okur.

---

## 2. Mimari

```
┌────────────────────────┐   saatlik cron    ┌──────────────────────────┐    curl     ┌───────────────────────────┐
│ VPS (okan-vps)         │ ────────────────► │ GitHub                   │ ◄────────── │ Claude Routine            │
│ binance_collector.py   │  git push -f      │ doruq-IT/kripto-brifing  │  raw URL    │ "Kripton Karar Sabah      │
│ → latest.json          │  (deploy key)     │ branch: market-data      │             │  Brifingi" 08:47 TSİ      │
└────────────────────────┘                   │ dosya: latest.json       │             │ → Telegram                │
                                             └──────────────────────────┘             └───────────────────────────┘
```

- Veri adresi (brifingin okuduğu): `https://raw.githubusercontent.com/doruq-IT/kripto-brifing/market-data/latest.json`
- `market-data` branch'i her yayında **tek commit** olarak yeniden yazılır (geçmiş şişmez). Yerel geçmiş VPS'te `snapshots.jsonl` içinde kalır.

---

## 3. GitHub reposu

- Repo: `doruq-IT/kripto-brifing`
- Kod branch'i: `claude/elegant-cori-lln6rd` (güncel geliştirme burada; `claude/binance-api-connection-test-4omj2z` üzerine devam ediyor. main'e henüz merge edilmedi, PR açılmadı)
- VPS'teki clone hâlâ eski branch'te (`claude/binance-api-connection-test-4omj2z`). `collector/` altında değişiklik olursa sunucuda önce `git fetch && git checkout claude/elegant-cori-lln6rd` gerekir.
- Veri branch'i: `market-data` (sadece `latest.json`, VPS otomatik yazar; elle dokunulmaz)

```
kripto-brifing/
├── README.md                     # Mimari + VPS kurulum adımları
├── PROJE_DURUMU.md               # Bu dosya
├── .gitignore                    # collector/data/ ve __pycache__ hariç tutulur
├── collector/
│   ├── binance_collector.py      # Binance public API'den veri çeker (API anahtarı gerekmez, sadece stdlib)
│   ├── publish.sh                # Toplayıcıyı çalıştırır + latest.json'ı market-data branch'ine push eder
│   └── data/                     # (git'e girmez) latest.json, snapshots.jsonl
└── briefing/
    └── routine_prompt.txt        # Routine'deki prompt'un birebir kaydı
```

### binance_collector.py — ne topluyor

Varsayılan 11 coin: **BTC, ETH, BNB, SOL, XRP, ADA, AVAX, LINK, LTC, BCH, SUI** (USDT perpetual). Liste `DEFAULT_SYMBOLS` içinde.

| Alan (latest.json) | Binance endpoint |
|---|---|
| price, change_24h_pct, high_24h, low_24h, range_24h_pct, quote_volume_24h_usdt | `/fapi/v1/ticker/24hr` |
| mark_price, funding_rate_pct, next_funding_time | `/fapi/v1/premiumIndex` |
| oi_usdt, oi_change_4h_pct, oi_change_24h_pct | `/futures/data/openInterestHist` (1h, son 25 saat) |
| global_long_short_ratio, global_long_pct | `/futures/data/globalLongShortAccountRatio` (4h) |
| top_trader_position_ls_ratio | `/futures/data/topLongShortPositionRatio` (4h) |
| taker_buy_sell_ratio | `/futures/data/takerlongshortRatio` (4h) |

`latest.json` üst alanları: `generated_at` (UTC), `source`, `ratio_period`, `coins[]`, `errors{}`.

Ortam değişkenleri: `SYMBOLS` (virgülle), `PERIOD` (varsayılan `4h`), `DATA_DIR`.

⚠️ Toplayıcıyı elle sembol vererek çalıştırmak (`binance_collector.py BNBUSDT ...`) yerel `latest.json`'ı sadece o coinlerle **ezer**. Bir sonraki cron çalışması 11 coinle düzeltir; GitHub'daki dosya sadece `publish.sh` çalışınca değişir.

---

## 4. VPS (sunucu) tarafı

Sunucu: **okan-vps** (Ubuntu 22.04, root). IP/SSH bilgileri Okan'da; bu public repoya yazılmadı.

Aynı sunucuda Okan'ın başka servisleri de çalışıyor (ayrıntılar Okan'da). **Onlara hiç dokunulmadı**; brifing toplayıcısı onlardan tamamen bağımsız, host üzerinde cron ile çalışır ve başka bir servisin ayarını/`.env`'ini kullanmaz.

### Klasör ve dosyalar

| Yol | Ne |
|---|---|
| `/opt/kripto-brifing/` | Repo clone'u (branch: `claude/binance-api-connection-test-4omj2z`) |
| `/opt/kripto-brifing/collector/data/latest.json` | Son snapshot (yerel) |
| `/opt/kripto-brifing/collector/data/snapshots.jsonl` | Tüm geçmiş (her satır bir coin snapshot'ı) |
| `/opt/kripto-brifing-publish/` | `publish.sh`'in her seferinde silip yeniden oluşturduğu geçici git klasörü |
| `~/.ssh/kripto_brifing_deploy` (+ `.pub`) | GitHub deploy key (repo'ya **yazma yetkili**). Private key hiçbir yere kopyalanmamalı |
| `/var/log/kripto-brifing.log` | Cron çıktısı; her başarılı çalışmanın sonunda `yayınlandı: HH:MMZ` |

### Cron (root crontab, `crontab -l`)

Crontab'da başka servislere ait satırlar da var; onlara dokunulmaz. Bu projeye ait tek satır:

```
30 * * * * /bin/bash /opt/kripto-brifing/collector/publish.sh >> /var/log/kripto-brifing.log 2>&1
```

### Sık kullanılan komutlar

```bash
# Kod güncellemesi (sadece collector/*.py veya publish.sh değiştiyse gerekir)
cd /opt/kripto-brifing && git pull

# Elle veri topla + yayınla
bash /opt/kripto-brifing/collector/publish.sh

# Sadece ekrana bas (yayınlamaz)
python3 /opt/kripto-brifing/collector/binance_collector.py

# Son çalışmalar
tail -20 /var/log/kripto-brifing.log
wc -l /opt/kripto-brifing/collector/data/snapshots.jsonl
```

Not: `briefing/routine_prompt.txt` değişiklikleri sunucuda `git pull` **gerektirmez**; prompt routine arayüzünden elle güncellenir.

---

## 5. Claude Routine

- Ad: **Kripton Karar Sabah Brifingi**
- ID: `trig_01Swxrg8zfpKMCuTfTBUAMJU`
- Düzenleme: https://claude.ai/code/routines/trig_01Swxrg8zfpKMCuTfTBUAMJU
- Zamanlama: `47 5 * * *` (UTC) = **her gün 08:47 TSİ**
- Bağlayıcı: Crypto.com (fiyatlar)
- Telegram gönderimi routine ortamındaki `TELEGRAM_BOT_TOKEN` ve `TELEGRAM_CHAT_ID` değişkenleriyle yapılıyor.
- ⚠️ Routine `http_api` ile oluşturulduğu için **Claude bu routine'i güncelleyemez**. Prompt değişikliklerini Okan elle yapıştırır. Claude'un görevi: `briefing/routine_prompt.txt`'yi güncelleyip push etmek ve tam metni sohbete yazmak.

### Veri kaynakları (brifingin kullandığı)

| Veri | Kaynak |
|---|---|
| Fiyat, 24s değişim, high/low | Crypto.com bağlayıcısı (BNB hariç; BNB Crypto.com'da yok → Binance verisinden) |
| Funding, OI, long/short, taker, aralık | GitHub `market-data/latest.json` (VPS'ten) |
| Korku-açgözlülük | `api.alternative.me/fng/?limit=2` |
| Haber, makro takvim | Web araması |

### Routine prompt'u (güncel, birebir — `briefing/routine_prompt.txt` ile aynı)

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
- Binance futures türev verisi: SADECE şu komutla al: curl -s "https://raw.githubusercontent.com/doruq-IT/kripto-brifing/market-data/latest.json" → her coin için funding_rate_pct (8 saatlik funding, yüzde), oi_usdt, oi_change_4h_pct, oi_change_24h_pct, global_long_pct (long hesap yüzdesi), top_trader_position_ls_ratio, taker_buy_sell_ratio (1'in altı = satıcı baskın), range_24h_pct. Bu veri Okan'ın VPS'inden saatlik yayınlanıyor. generated_at alanı 3 saatten eskiyse, dosya alınamazsa veya coins boşsa türev maddesine "Binance verisi alınamadı" yaz ve bu verideki hiçbir rakamı kullanma. Fiyat için ana kaynak Crypto.com olarak kalsın; Crypto.com fiyatı alınamazsa bu dosyadaki price/high_24h/low_24h yedek olarak kullanılabilir. Dosyada olmayan, errors alanında geçen veya ilgili alanı null olan coin için o rakamı "veri yok" yaz, tahmin etme; bu coini 8. maddede gruplama, maddenin sonuna "Veri yok: <coinler>" diye ekle.
- Korku-açgözlülük endeksi: SADECE şu komutla al: curl -s "https://api.alternative.me/fng/?limit=2" → bugünkü değer, sınıfı ve dünkü değer. Başka site kullanma.
- Haberler ve makro takvim: web araması. Tek kaynağa dayanan haberi, iddiayı veya rakamı her seferinde "doğrulanmadı" diye işaretle. Rakam uydurma; bulamadığını "alınamadı" yaz.

DİL (en önemli kural)
- Okan mesajı telefonda, sabah hızlıca okuyacak. Her maddeyi ilk okuyuşta anlaşılacak kadar basit ve net yaz.
- Kısa cümleler kur. Bir cümlede tek fikir olsun.
- Teknik terim kullanırsan yanına kısa Türkçe karşılığını yaz: OI = açık pozisyon miktarı, funding = long/short arasındaki periyodik ödeme, liq = likidasyon.
- 4., 8., 9. ve 10. maddelerde rakamı verdikten sonra "→" ile tek cümlelik "bu ne demek" açıklaması ekle. Örn: "BCH: açık pozisyon 24 saatte -%19,6 → çok sayıda pozisyon kapanmış ya da likide olmuş olabilir."
- Belirsiz ifade kullanma: "risk artabilir" deme; kimin için (long mu short mu tutan) ve hangi risk (likidasyon, yeni dip, sert düşüş, sert yükseliş) olduğunu yaz.
- Türev verisinden çıkarımları "olabilir", "olası" gibi temkinli dille yaz; kesin hüküm kurma.

FORMAT (düz metin, en fazla 11 madde, her madde en fazla 3 satır, toplam 3800 karakteri geçme)
- Hiç link, URL, köşeli parantez veya Markdown kullanma. Kaynakları sadece adıyla yaz.
- Yüzdeleri Türkçe biçimde yaz: -%2,19 / +%0,24. Pozitif değerlerde + işaretini yaz; bu kural funding ve OI değişimi dahil tüm yüzdeler için geçerli (örn: funding +%0,0061).
- Maddeleri "1.", "2." biçiminde numarala ve her maddeye kısa bir başlık koy (örn: "4. Türev radarı:").
- 8. ve 9. maddeler işlem önerisi değildir: "al", "sat", "gir", "long aç", "short aç" gibi ifadeler, giriş seviyesi veya hedef fiyat yazma. 🟢 işareti "işlem aç" anlamına gelmez, sadece bugünkü verinin Okan'ın kurallarıyla çelişmediğini gösterir.
Başlık: "☀️ Sabah Brifingi — GG.AA.YYYY HH:MM TSİ"
1. Piyasa: BTC ve ETH fiyatı, 24s değişim, gün aralığındaki konum ((fiyat-low)/(high-low)): %0-25 "günün dibine yakın", %25-75 "günün ortasında", %75-100 "günün tepesine yakın"
2. Düşen/yükselen: en çok düşen ve yükselen 3'er büyük coin (tek satır)
3. Piyasa havası: korku-açgözlülük bugünkü değer + sınıf, dünkü değer (Alternative.me). Sınıfı Türkçe yaz: Aşırı Korku, Korku, Nötr, Açgözlülük, Aşırı Açgözlülük
4. Türev radarı (Binance): BTC ve ETH için funding, 24s açık pozisyon (OI) değişimi, long hesap yüzdesi. Ayrıca listeden en uç sinyali veren 1-2 coin (en yüksek/negatif funding, en büyük 24s OI değişimi veya long hesap oranı %70 üstü). Anlamlandırma: OI artışı = yeni pozisyon birikiyor; fiyat düşerken sert OI düşüşü = pozisyonlar kapanmış ya da likide olmuş olabilir; long hesap %70 üstü = kalabalık long, ters harekette toplu likidasyon riski.
5. Haberler: en fazla 2 önemli haber, her biri tek cümle. Tek kaynaklı iddia ve rakamları "doğrulanmadı" diye işaretle
6. Takvim: bugün ve yarın önemli makro veriler, gün adı ve TSİ saatiyle
7. Liq radarı: 24s aralığı ((high-low)/low) en geniş 3 coin ve bu aralığın 5x liq mesafesine (~%20) oranı. Örn: "BCH günde %9,1 oynadı → liq mesafenin %46'sı kadar"
8. Kurallarına uygunluk: listedeki 11 coini Binance verisine göre üç gruba ayır, her grupta coin adı ve belirleyici rakam, sonra "→" ile tek cümle açıklama:
   🟢 Kurallarınla çelişmiyor: 24s aralık ≤ %5 (liq mesafenin ≤ %25'i) VE long hesap oranı < %70 VE |OI 24s değişimi| < %10
   🔴 Bugün kurallarına uymuyor: 24s aralık ≥ %10 (liq mesafenin ≥ yarısı) VEYA |OI 24s değişimi| ≥ %15 VEYA 24s fiyat değişimi ≤ -%5
   🟡 Temkinli: geri kalanlar (en belirleyici nedeni yaz: kalabalık long, geniş aralık veya OI hareketi)
   Binance verisi alınamadıysa bu maddeye "Binance verisi olmadan filtre uygulanamadı" yaz.
9. Kritik seviyeler: en fazla 2 tane, BTC/ETH veya 4. maddede öne çıkan coin için 24s high/low seviyesine dayalı. Biçim: "<coin> <seviye> altına inerse (günün dibi) → long tutanlar için likidasyon zinciri riski artabilir" veya "<coin> <seviye> üstüne çıkarsa (günün tepesi) → short tutanlar için sert yükseliş riski artabilir". Seviyenin ne olduğunu (günün dibi/tepesi) ve kimin için hangi risk olduğunu mutlaka yaz. Yön tahmini veya işlem önerisi yapma.
10. ⚠️ Bugün dikkat: kurallar ve hata müzesine göre tek ana uyarı, en az bir somut sayıyla (4., 7. veya 8. maddeden ya da makro saatinden). Kalabalık long + yükselen OI varsa bunu "herkes alıyor"/FOMO hatasıyla ilişkilendirebilirsin. Sert OI düşüşü olan coinlerde "dipten döner" diyip zarardaki pozisyona ekleme riskini hatırlat. Her gün aynı cümleyi kurma. Sade dille, en fazla 3 satır.
11. Radar: "Bugün hangi coinleri izliyorsun?"
Son satır: "Kaynaklar:" ve kaynak adları, virgülle ayrılmış (sadece yayın/site adı; Binance verisi kullanıldıysa "Binance Futures" ekle). Kaynak adlarına saat, sayı, tarih veya başka metin ekleme.

GÖNDERİM
Metni /tmp/brifing.txt dosyasına yaz. Göndermeden önce Markdown linklerini temizle:
sed -i -E 's/\[([^]]+)\]\([^)]+\)/\1/g; s#https?://[^ )]+##g' /tmp/brifing.txt
Karakter sayısını `wc -m /tmp/brifing.txt` ile kontrol et; 3800'ü geçiyorsa önce 5. ve 6. maddeleri, sonra 2. maddeyi kısaltıp tekrar yaz.
Göndermeden önce metni bir kez oku: her madde tek okuyuşta anlaşılıyor mu, "risk artabilir" gibi kimin için olduğu belirsiz bir ifade kaldı mı, son satırda kaynak adları dışında metin var mı? Varsa düzelt.
Sonra gönder (token'ı asla yazdırma):
curl -sS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" --data-urlencode "text@/tmp/brifing.txt" -d "disable_web_page_preview=true" -w "\nHTTP %{http_code}\n"
HTTP 200 ve "ok":true değilse hatayı raporla. Başarılıysa tek cümleyle "gönderildi" yaz.
```

---

## 6. Okan'ın profili (brifingin dayandığı kurallar)

- Kasa ~500 USDT, sadece futures, 5x isolated, işlem başı 50 USDT marj, en fazla 5 pozisyon.
- TP %10 ROE (≈%2 fiyat), SL yok, liq'e yakın bir kez ekleme. 5x'te ~%20 ters hareket = liq.
- Başa baş için ~%91 isabet gerekiyor (kazanç ≈ +5 USDT, kayıp ≈ -50/-100 USDT). Bu yapısal risk Okan'a açıkça söylendi.
- Sadece büyük/stabil coin; memecoin ve volatil coin yok.
- Brifing **al/sat tavsiyesi vermez**. 8. madde (🟢/🟡/🔴 filtre) ve 9. madde (kritik seviyeler) sadece kurallara uygunluk ve risk seviyelerini gösterir.

---

## 7. Alınan kararlar ve gerekçeleri

| Karar | Gerekçe |
|---|---|
| Proxy/Cloudflare ile Binance'e erişim **yok** | Konum kontrolünü atlatmak Binance şartlarına aykırı; Cloudflare IP'leri de sık engelleniyor |
| Veri VPS'te toplanır, GitHub'a yayınlanır | Okan'ın kendi sunucusu uygun bölgede; brifing sadece hazır veriyi okur |
| `market-data` branch'i tek commit, force-push | Repo geçmişi şişmesin |
| Toplayıcı sadece stdlib | Sunucuda ek kurulum gerekmesin |
| DOT çıkarıldı | Binance OI ~38M$, listenin en sığ piyasası; ani iğne riski |
| BNB eklendi | İlk 5 coin, OI ~441M$, oynaklığı düşük |
| TRX eklenmedi (opsiyonel) | Stabil ama günlük hareketi dar; %2 TP için yavaş olabilir. Funding belirgin negatifti (-%0,0266) |
| HYPE, DOGE, ZEC eklenmedi | Yeni/volatil veya memecoin; kurallara aykırı |
| Prompt'a "DİL" bölümü | Okan brifingi ilk okuyuşta anlayabilsin; her rakamdan sonra "→ bu ne demek" |
| 9. madde kimin için hangi risk olduğunu yazar | "risk artabilir" tek başına belirsizdi |

---

## 8. Doğrulanmış durum (28.09.2026)

- ✅ VPS'ten Binance erişimi çalışıyor (HTTP 200)
- ✅ Deploy key eklendi, `publish.sh` başarılı (`yayınlandı: 14:25Z`)
- ✅ GitHub'daki `latest.json` bulut ortamından okunabiliyor, 11 coin (BNB dahil, DOT yok), `errors: {}`
- ✅ Cron kurulu (`30 * * * *`)
- ✅ Routine elle çalıştırıldı; Binance rakamları brifingte veriyle birebir tutuyor
- ⏳ Yeni prompt (BNB'li + DİL bölümlü) ile **ilk otomatik brifing: 29.09.2026 08:47 TSİ**

---

## 9. Sıradaki adımlar / açık konular

1. **29.09 sabahı ilk otomatik brifingi kontrol et:** BNB fiyatı var mı (Binance'ten), 8. maddede 11 coin gruplanmış mı, kaynaklar satırı temiz mi.
2. **Bir hafta prompt'a dokunmadan izle**, sonra toplu ayar yap (öneri buydu).
3. Bilinen küçük pürüzler (şimdilik bilerek bırakıldı):
   - Dallas Fed gibi küçük makro verilerde saat tutarsız / eksik olabiliyor.
   - Crypto.com ve Binance 24s değişimleri farklı borsalar olduğu için küçük farklar gösterebiliyor (normal).
4. Opsiyonel fikirler (Okan henüz onaylamadı):
   - TRX'i listeye eklemek.
   - `snapshots.jsonl` geçmişinden haftalık özet (OI/funding trendi).
   - Kod branch'ini main'e merge etmek (PR açılmadı).
5. Sunucu güvenliği: bu projenin kapsamı dışında; Okan'a ayrıca hatırlatıldı. Ayrıntılar public repoya yazılmaz.

---

## 10. Yeni oturumda nasıl devam edilir

Yeni Claude oturumunda (repo `doruq-IT/kripto-brifing`, branch `claude/elegant-cori-lln6rd`) şunu yaz:

> `PROJE_DURUMU.md` dosyasını oku. Kripto brifing projesine kaldığımız yerden devam edeceğiz. [yapmak istediğin şey]

Çalışma kuralları (önceki oturumda oturan düzen):
- Claude, VPS'e bağlanamaz; sunucuda çalıştırılacak komutları yazar, Okan çalıştırıp çıktıyı yapıştırır.
- Claude, routine'i güncelleyemez; `briefing/routine_prompt.txt`'yi güncelleyip push eder ve **tam metni** sohbete yazar, Okan yapıştırır.
- Sunucuda `git pull` sadece `collector/` altındaki dosyalar değiştiğinde gerekir; Claude bunu ayrıca söyler.
- Adım adım ilerlenir; her adımdan sonra çıktı kontrol edilir.
- Brifing hiçbir koşulda al/sat tavsiyesi, giriş seviyesi veya hedef fiyat vermez.
