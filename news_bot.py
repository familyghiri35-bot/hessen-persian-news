import json
import os
import re
from html import unescape
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from google import genai

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
CHANNEL_ID = "@HessenPersian"
POSTED_FILE = "posted.txt"

SOURCE_URLS = [
    "https://www.hessenschau.de/index~rss.xml",
    "https://www.hessenschau.de/aktuelles/index.html",
    "https://www.fr.de/hessen/index.rss",
    "https://www.fr.de/hessen/",
    "https://www.hessen.de/rss.xml",
    "https://www.hessen.de/presse",
]

WEATHER_WORDS = [
    "wetter",
    "unwetter",
    "frost",
    "glaette",
    "glätte",
    "schnee",
    "regen",
    "sturm",
    "nebel",
    "temperatur",
    "dwd",
    "hitzewelle",
    "gewitter",
]

client = genai.Client(api_key=GEMINI_API_KEY)


def load_posted():
    if not os.path.exists(POSTED_FILE):
        return set()
    with open(POSTED_FILE, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
    return {x.strip() for x in lines if x.strip()}


def save_posted(link):
    with open(POSTED_FILE, "a", encoding="utf-8") as f:
        f.write(link + "\n")


def fetch_url_text(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    }
    req = Request(url, headers=headers)
    with urlopen(req, timeout=20) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="ignore")


def parse_items(content, base_url):
    found = []
    seen = set()

    for m in re.finditer(r"<item\b[^>]*>(.*?)</item>", content, re.IGNORECASE | re.DOTALL):
        block = m.group(1)
        tm = re.search(r"<title>(.*?)</title>", block, re.IGNORECASE | re.DOTALL)
        lm = re.search(r"<link>(.*?)</link>", block, re.IGNORECASE | re.DOTALL)
        if tm and lm:
            title = " ".join(unescape(re.sub(r"<[^>]+>", " ", tm.group(1))).split())
            link = unescape(re.sub(r"<[^>]+>", "", lm.group(1))).strip()
            if title and link.startswith("http") and link not in seen:
                seen.add(link)
                found.append({"title": title, "summary": title, "link": link})

    if found:
        return found

    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', content, re.IGNORECASE | re.DOTALL):
        href = m.group(1).strip()
        title = " ".join(unescape(re.sub(r"<[^>]+>", " ", m.group(2))).split())
        full_url = urljoin(base_url, href)
        if len(title) < 25 or not full_url.startswith("https://"):
            continue
        if any(bad in full_url for bad in ["#", "/suche", "/kontakt", "/impressum", "/datenschutz", "login"]):
            continue
        if full_url not in seen:
            seen.add(full_url)
            found.append({"title": title, "summary": title, "link": full_url})

    return found


def is_weather(title, summary, link):
    text = (title + " " + summary + " " + link).lower()
    return any(w in text for w in WEATHER_WORDS)


def build_prompt(title, summary, link):
    if is_weather(title, summary, link):
        parts = [
            "یک گزارش هواشناسی کوتاه، دقیق و رسمی برای کانال تلگرام بنویس که وضعیت فعلی و چشم‌انداز دست‌کم دو روز آینده ایالت هسن آلمان را پوشش دهد.",
            "از اطلاعات زیر استفاده کن و اگر بازه دو روز آینده در متن منبع نبود، به‌طور شفاف به وضعیت گزارش‌شده و چشم‌انداز دو روز آینده بر
