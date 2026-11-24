import datetime
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
MODELS = ["gemini-3.5-flash-lite", "gemini-3.8-flash"]

DWD_URL = (
    "https://www.dwd.de/DE/wetter/"
    "wetterundklima_vorort/hessen/hessen_node.html"
)
NEWS_URLS = [
    "https://www.fr.de/hessen/",
    "https://www.hessen.de/presse",
]

BAD_PARTS = [
    "#",
    "/suche",
    "/kontakt",
    "/impressum",
    "/datenschutz",
    "login",
    "archiv",
    "facebook.com",
    "social.bund.de",
    "instagram.com",
    "youtube.com",
    "x.com",
    "twitter.com",
]

W_HEADS = (
    "\u067e\u06cc\u0634\u200c\u0628\u06cc\u0646\u06cc \u0648\u0636\u0639 "
    "\u0647\u0648\u0627\u06cc \u0627\u06cc\u0627\u0644\u062a \u0647\u0633\u0646 (DWD), "
    "\u0648\u0636\u0639\u06cc\u062a \u0641\u0639\u0644\u06cc \u0648 "
    "\u0686\u0634\u0645\u200c\u0627\u0646\u062f\u0627\u0632 \u062f\u0648 \u0631\u0648\u0632 "
    "\u0622\u06cc\u0646\u062f\u0647\u060c \u062f\u0645\u0627 "
    "(\u0641\u0631\u0627\u0646\u06a9\u0641\u0648\u0631\u062a \u0648 \u0647\u0633\u0646)\u060c "
    "\u0628\u0627\u0631\u0634 \u0648 \u0628\u0627\u062f\u060c "
    "\u062a\u0648\u0635\u06cc\u0647 \u0648 \u067e\u0648\u0634\u0634."
)
SRC_WORD = "\u0645\u0646\u0628\u0639:"

client = genai.Client(api_key=API_KEY)


def log(msg):
    print(msg, flush=True)


def load_posted():
    if not os.path.exists(POSTED_FILE):
        return set()
    with open(POSTED_FILE, "r", encoding="utf-8") as f:
        return {x.strip() for x in f.read().splitlines() if x.strip()}


def save_posted(key):
    with open(POSTED_FILE, "a", encoding="utf-8") as f:
        f.write(key + NL)


def fetch_text(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=10) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def clean_html(raw):
    no_s = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", raw, flags=re.I | re.S)
    no_t = re.sub(r"<[^>]+>", " ", no_s)
    return " ".join(unescape(no_t).split())


def parse_news(html, base):
    out = []
    seen = set()
    for m in re.finditer(r"<a\b[^>]*>(.*?)</a>", html, re.I | re.S):
        head = html[m.start():m.start() + 250]
        hm = re.search(r"href=[\x27\x22]([^\x27\x22]+)[\x27\x22]", head, re.I)
        if not hm:
            continue
        t = clean_html(m.group(1))
        u = urljoin(base, hm.group(1).strip())
        low_u = u.lower().rstrip("/")
        if len(t) < 25 or not u.startswith("https://"):
            continue
        if low_u in ["https://www.fr.de", "https://www.hessen.de"]:
            continue
        if any(b in low_u for b in BAD_PARTS):
            continue
        if u not in seen:
            seen.add(u)
            out.append({"title": t, "link": u})
    return out


def ask_models(prompt):
    last_err = None
    for mod in MODELS:
        try:
            res = client.models.generate_content(model=mod, contents=prompt)
            txt = (res.text or "").strip()
            if txt:
                log("MODEL_OK " + mod)
                return txt
        except Exception as e:
            last_err = e
            err_s = str(e)
            log("MODEL_ERR " + mod + " -> " + err_s)
            if "429" in err_s or "RESOURCE_EXHAUSTED" in err_s:
                raise
            time.sleep(3)
    if last_err:
        raise last_err
    return ""


def send_tg(text):
    url = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": False}
    raw = json.dumps(data).encode("utf-8")
    req = Request(
        url,
        data=raw,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=15) as resp:
        resp.read()


def run_weather(posted, quota_hit):
    today_key = "weather:" + datetime.date.today().isoformat()
    if quota_hit or today_key in posted:
        return 0, quota_hit
    try:
        plain = clean_html(fetch_text(DWD_URL))[:4500]
        p1 = "Write a concise formal Persian weather forecast for Hessen."
        p2 = "Base it strictly on the DWD text below without fake temps."
        p3 = "Cover current weather, tomorrow, and next 2 days."
        p4 = "Use bold headings for: " + W_HEADS
        p5 = "End with: " + SRC_WORD + " DWD / " + DWD_URL + " and @HessenPersian."
        p6 = "Return only Persian text. DWD_TEXT: " + plain
        txt = ask_models(NL.join([p1, p2, p3, p4, p5, p6]))
        if txt:
            send_tg(txt)
            save_posted(today_key)
            posted.add(today_key)
            return 1, False
    except Exception as e:
        err_s = str(e)
        log("W_ERR -> " + err_s)
        if "429" in err_s or "RESOURCE_EXHAUSTED" in err_s:
            return 0, True
    return 0, False


def main():
    t0 = time.time()
    posted = load_posted()
    quota_hit = False
    w_done, quota_hit = run_weather(posted, quota_hit)

    items = []
    seen = set()
    for src in NEWS_URLS:
        if quota_hit or time.time() - t0 > 45:
            break
        try:
            got = parse_news(fetch_text(src), src)
            log("OK " + src + " -> " + str(len(got)))
            for it in got:
                if it["link"] not in seen:
                    seen.add(it["link"])
                    items.append(it)
        except Exception as e:
            log("ERR " + src + "
