import json
import os
import re
import socket
import time
from html import unescape
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from google import genai

socket.setdefaulttimeout(12)

NL = chr(10)
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
CHANNEL_ID = "@HessenPersian"
POSTED_FILE = "posted.txt"
GEMINI_MODEL = "gemini-3.8-flash"

SOURCE_URLS = [
    "https://www.hessenschau.de/index~rss.xml",
    "https://www.hessenschau.de/aktuelles/index.html",
    "https://www.fr.de/hessen/index.rss",
    "https://www.fr.de/hessen/",
    "https://www.hessen.de/rss.xml",
    "https://www.hessen.de/presse",
    "https://www.dwd.de/DE/wetter/wetterundklima_vorort/hessen/hessen_node.html",
]

WEATHER_WORDS = [
    "wetter", "unwetter", "frost", "glaette", "glätte",
    "schnee", "regen", "sturm", "nebel", "temperatur",
    "dwd", "hitzewelle", "gewitter",
]

client = genai.Client(api_key=GEMINI_API_KEY)


def log(msg):
    print(msg, flush=True)


def load_posted():
    if not os.path.exists(POSTED_FILE):
        return set()
    with open(POSTED_FILE, "r", encoding="utf-8") as f:
        return {x.strip() for x in f.read().splitlines() if x.strip()}


def save_posted(link):
    with open(POSTED_FILE, "a", encoding="utf-8") as f:
        f.write(link + NL)


def fetch_url_text(url):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    req = Request(url, headers=headers)
    with urlopen(req, timeout=10) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def clean_text(raw_html):
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", raw_html)).split())


def parse_items(content, base_url):
    found = []
    seen = set()
    for m in re.finditer(r"<item\b[^>]*>(.*?)</item>", content, re.IGNORECASE | re.DOTALL):
        block = m.group(1)
        tm = re.search(r"<title>(.*?)</title>", block, re.IGNORECASE | re.DOTALL)
        lm = re.search(r"<link>(.*?)</link>", block, re.IGNORECASE | re.DOTALL)
        if tm and lm:
            title = clean_text(tm.group(1))
            link = unescape(re.sub(r"<[^>]+>", "", lm.group(1))).strip()
            if title and link.startswith("http") and link not in seen:
                seen.add(link)
                found.append({"title": title, "summary": title, "link": link})
    if found:
        return found
    for m in re.finditer(r"<a\b[^>]*>(.*?)</a>", content, re.IGNORECASE | re.DOTALL):
        tag_open = content[m.start():m.start() + 250]
        hm = re.search(r'href=["\']([^"\']+)["\']', tag_open, re.IGNORECASE)
        if not hm:
            continue
        title = clean_text(m.group(1))
        full_url = urljoin(base_url, hm.group(1).strip())
        if len(title) < 25 or not full_url.startswith("https://"):
            continue
        if any(b in full_url for b in ["#", "/suche", "/kontakt", "/impressum", "/datenschutz", "login"]):
            continue
        if full_url not in seen:
            seen.add(full_url)
            found.append({"title": title, "summary": title, "link": full_url})
    return found


def is_weather(title, summary, link):
    text = (title + " " + summary + " " + link).lower()
    return any(w in text for w in WEATHER_WORDS)


def build_prompt(title, summary, link, force_weather=False):
    if force_weather or is_weather(title, summary, link):
        p1 = "Write a concise formal Persian weather forecast for Hessen, Germany "
        p2 = "covering current conditions, tomorrow, and the next 2 days based on
