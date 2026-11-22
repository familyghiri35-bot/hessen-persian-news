import os
import re
from html import unescape
from urllib.parse import urljoin
import feedparser
import requests
from google import genai

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
CHANNEL_ID = "@HessenPersian"
POSTED_FILE = "posted.txt"

RSS_CANDIDATES = [
    "https://www.hessenschau.de/index~rss.xml",
    "https://www.hessenschau.de/rss.xml",
    "https://www.hessenschau.de/feed.xml",
    "https://www.fr.de/hessen/index.rss",
    "https://www.fr.de/hessen/rss.xml",
    "https://www.fr.de/hessen/?service=rss",
    "https://www.hessen.de/rss.xml",
    "https://www.hessen.de/service/rss.xml",
]

HTML_SOURCES = [
    "https://www.hessenschau.de/aktuelles/index.html",
    "https://www.hessenschau.de/index.html",
    "https://www.fr.de/hessen/",
    "https://www.hessen.de/presse",
]

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

WEATHER_KEYWORDS = [
    "wetter", "unwetter", "frost", "glätte", "schnee", "regen",
    "sturm", "nebel", "temperatur", "dwd", "hitzewelle", "gewitter",
]

client = genai.Client(api_key=GEMINI_API_KEY)


def load_posted_links():
    if not os.path.exists(POSTED_FILE):
        return set()
    with open(POSTED_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def save_posted_link(link):
    with open(POSTED_FILE, "a", encoding="utf-8") as f:
        f.write(link + "\n")


def is_weather_item(title, summary, link):
    combined = (title + " " + summary + " " + link).lower()
    return any(re.search(r"\b" + re.escape(kw), combined) for kw in WEATHER_KEYWORDS)


def build_weather_prompt(title, summary, link):
    lines = [
        "یک گزارش هواشناسی کوتاه، دقیق و رسمی برای کانال تلگرام بنویس که وضعیت فعلی و چشم‌انداز دست‌کم دو روز آینده ایالت هسن آلمان را پوشش دهد.",
        "از اطلاعات زیر استفاده کن و اگر بازه دو روز آینده در متن منبع نبود، به‌طور شفاف به وضعیت گزارش‌شده و چشم‌انداز دو روز آینده بر اساس الگوهای هواشناسی هسن و DWD اشاره کن بدون ساختن عدد دمای جعلی:",
        "",
        "عنوان منبع: " + title,
        "خلاصه منبع: " + summary,
        "لینک منبع: " + link,
        "",
        "قالب خروجی را دقیقاً به این شکل و به زبان فارسی روان بنویس:",
        "**پیش‌بینی وضع هوای ایالت هسن (گزارش DWD)**",
        "**تاریخ و چشم‌انداز:** وضعیت فعلی و پیش‌بینی حداقل تا دو روز آینده",
        "",
        "**وضعیت کلی و روند دو روز آینده:** ...",
        "**دما (فرانکفورت و شهرهای شاخص هسن):** ...",
        "**بارش و باد:** ...",
        "**پوشش و توصیه‌های کاربردی:** ...",
        "",
        "**منبع:** DWD / " + link,
