"""Telegram'a düz metin mesaj gönderir (sadece stdlib).

Kimlik bilgileri repoda DEĞİL, sunucuda ENV_FILE (varsayılan /etc/kripto-brifing.env,
izin 600) içinde durur:
  KRIPTO_TG_TOKEN=...
  KRIPTO_TG_CHAT=...
Aynı adlı ortam değişkenleri dosyadan önceliklidir.

DRY_RUN=1 ortam değişkeni veya dosyada DRY_RUN=1 satırı varsa mesaj gönderilmez,
ekrana (cron'da log'a) basılır. Kimlik bilgisi yoksa da kuru çalışır.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ENV_FILE = os.getenv("KRIPTO_ENV_FILE", "/etc/kripto-brifing.env")
MAX_LEN = 4000  # Telegram sınırı 4096


def load_env(path=None):
    vals = {}
    try:
        with open(path or ENV_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    vals[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    for k in ("KRIPTO_TG_TOKEN", "KRIPTO_TG_CHAT", "DRY_RUN"):
        if os.getenv(k):
            vals[k] = os.getenv(k)
    return vals


def dry_run(env=None):
    env = env if env is not None else load_env()
    return env.get("DRY_RUN") == "1" or not (env.get("KRIPTO_TG_TOKEN") and env.get("KRIPTO_TG_CHAT"))


def send(text):
    """True: gönderildi (veya kuru çalıştırma). False: hata (token asla yazdırılmaz)."""
    env = load_env()
    text = text[:MAX_LEN]
    if dry_run(env):
        print("[KURU ÇALIŞTIRMA — gönderilmedi]\n" + text)
        return True
    data = urllib.parse.urlencode({
        "chat_id": env["KRIPTO_TG_CHAT"], "text": text, "disable_web_page_preview": "true",
    }).encode()
    url = f"https://api.telegram.org/bot{env['KRIPTO_TG_TOKEN']}/sendMessage"
    try:
        with urllib.request.urlopen(url, data=data, timeout=15) as resp:
            ok = json.loads(resp.read().decode()).get("ok") is True
    except urllib.error.HTTPError as e:
        print(f"telegram: HTTP {e.code} {e.read().decode()[:200]}", file=sys.stderr)
        return False
    except Exception as e:  # ağ hatası: URL (token içerir) yazdırılmaz
        print(f"telegram: bağlantı hatası ({type(e).__name__})", file=sys.stderr)
        return False
    if not ok:
        print("telegram: yanıt ok değil", file=sys.stderr)
    return ok
