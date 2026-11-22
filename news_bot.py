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
        return set(line.strip() for line in f
