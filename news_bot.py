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
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
API_KEY = os.environ["GEMINI_API_KEY"]
CHAT_ID = "@HessenPersian"
POSTED_FILE = "posted.txt"
MODEL_NAME = "gemini-3.8-flash"

URLS = [
    "https://www.fr.de/hessen/",
    "https://www.hessen.de/presse",
    "https://www.dwd.de/DE/wetter/wetterundklima_vorort/hessen/hessen_node.html",
]

W_KEYS = [
    "wetter", "unwetter", "frost", "glaette", "glätte",
    "schnee", "regen", "sturm", "nebel", "temperatur",
    "dwd", "hitzewelle", "gewitter",
]

BAD_PARTS = [
    "#", "/suche", "/kontakt", "/impressum", "/datenschutz", "login",
    "archiv", "facebook.com", "social.bund.de", "instagram.com",
    "youtube.com", "x.com", "twitter.com",
    "berlin-brandenburg", "mecklenburg-vorpommern", "niedersachsen-bremen",
    "rheinland-pfalz-saarland", "schleswig-holstein-hamburg", "bayern",
]

client = genai.Client(api_key=API_KEY)


def log(msg):
    print(msg, flush=True)


def load_posted():
    if not os.path.exists(POSTED_FILE):
        return set()
    with open(POSTED_FILE, "r", encoding="utf-8") as f:
        return {line.strip() for line in f.read().splitlines() if line.strip()}


def save_posted(link):
    with open(POSTED_FILE, "a", encoding="utf-8") as f:
        f.write(link + NL)


def fetch_text(url):
    hdrs = {"User-Agent": "Mozilla/5.0"}
    req = Request(url, headers=hdrs)
    with urlopen(req, timeout=10) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def clean_html(raw):
    no_tag = re.sub(r"<[^>]+>", " ", raw)
    return " ".join(unescape(no_tag).split())


def parse_items(html, base):
    out = []
    seen = set()
    for m in re.finditer(r"<a\b[^>]*>(.*?)</a>", html, re.I | re.S):
        head = html[m.start():m.start() + 250]
        hm = re.search(r"href=[\x27\x22]([^\x27\x22]+)[\x27\x22]", head, re.I)
        if not hm:
            continue
        t = clean_html(m.group(1))
        u = urljoin(base, hm.group(1).strip())
        low_u = u.lower()
        if len(t) < 25 or not u.startswith("https://"):
            continue
        if any(b in low_u for b in BAD_PARTS):
            continue
        if u not in seen:
            seen.add(u)
            out.append({"title": t, "summary": t, "link": u})
    return out


def is_weather(item):
    blob = (item["title"] + " " + item["summary"] + " " + item["link"]).lower()
    return any(k in blob for k in W_KEYS)


def make_prompt(item, force_weather=False):
    t = item["title"]
    s = item["summary"]
    u = item["link"]
    if force_weather or is_weather(item):
        parts = [
            "Write a concise formal Persian weather forecast for Hessen, Germany.",
            "Include current status, tomorrow, and next 2 days based on DWD without fake temperatures.",
            "Use bold headings for: پیش‌بینی وضع هوای ایالت هسن (DWD), وضعیت فعلی و چشم‌انداز دو
