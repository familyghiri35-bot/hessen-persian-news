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


def clean_html_text(raw_html):
    no_tags = re.sub(r"<[^>]+>", " ", raw_html)
    return " ".join(unescape(no_tags).split())


def parse_items(content, base_url):
    found = []
    seen = set()

    item_pat = re.compile(r"<item\b[^>]*>(.*?)</item>", re.IGNORECASE | re.DOTALL)
    title_pat = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
    link_pat = re.compile(r"<link>(.*?)</link>", re.IGNORECASE | re.DOTALL)

    for m in item_pat.finditer(content):
        block = m.group(1)
        tm = title_pat.search(block)
        lm = link_pat.search(block)
        if tm and lm:
            title = clean_html_text(tm.group(1))
            link = unescape(re.sub(r"<[^>]+>", "", lm.group(1))).strip()
            if title and link.startswith("http") and link not in seen:
                seen.add(link)
                found.append({"title": title, "summary": title, "link": link})

    if found:
        return found

    anchor_pat = re.compile(r"<a\b[^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
    href_pat = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)

    for m in anchor_pat.finditer(content):
        tag_open = content[m.start():m.start() + 250]
        hm = href_pat.search(tag_open)
        if not hm:
            continue
        href = hm.group(1).strip()
        title = clean_html_text(m.group(1))
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


def weather_header():
    h1 = "**\u067e\u06cc\u0634\u200c\u0628\u06cc\u0646\u06cc \u0648\u0636\u0639 \u0647\u0648\u0627\u06cc \u0627\u06cc\u0627\u0644\u062a \u0647\u0633\u0646 (DWD)**"
    h2 = "**\u0648\u0636\u0639\u06cc\u062a \u0641\u0639\u0644\u06cc\u060c \u0641\u0631\u062f\u0627 \u0648 \u0686\u0634\u0645\u200c\u0627\u0646\u062f\u0627\u0632 \u062f\u0648 \u0631\u0648\u0632 \u0622\u06cc\u0646\u062f\u0647:** ..."
    h3 = "**\u062f\u0645\u0627 (\u0641\u0631\u0627\u0646\u06a9\u0641\u0648\u0631\u062a \u0648 \u0647\u0633\u0646):** ..."
    h4 = "**\u0628\u0627\u0631\u0634 \u0648 \u0628\u0627\u062f:** ..."
    h5 = "**\u062a\u0648\u0635\u06cc\u0647 \u0648 \u067e\u0648\u0634\u0634:** ..."
    return "\n".join([h1, h2, h3, h4, h5])


def build_weather_prompt(title, summary, link):
    tpl = weather_header()
    footer = "\n**\u0645\u0646\u0628\u0639:** DWD / " + link + "\n@HessenPersian"
    msg = "Write a concise formal Persian weather forecast for Hessen, Germany, covering current status, tomorrow, and the next 2 days based on the source and DWD patterns without inventing fake temperatures.\n"
    msg = msg + "Replace '...' in this template and keep the footer:\n" + tpl + footer + "\n"
    msg = msg + "Return only the final Persian post.\nTitle: " + title + "\nSummary: " + summary
    return msg


def build_news_prompt(title, summary, link):
    src_line = "\u0645\u0646\u0628\u0639: " + link
    msg = "Write a concise, formal Persian Telegram news post with a bold headline on line 1, followed by 2 to 4 formal Persian summary sentences starting with '- ', then '" + src_line + "' and '@HessenPersian'.\n"
    msg = msg + "Return only the final Persian post.\nTitle: " + title + "\nSummary: " + summary
    return msg


def format_post(title, summary, link, force_weather=False):
    if force_weather or is_weather(title, summary, link):
        prompt = build_weather_prompt(title, summary, link)
    else:
        prompt = build_news_prompt(title, summary, link)

    resp = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    return (resp.text or "").strip()


def send_to_telegram(text):
