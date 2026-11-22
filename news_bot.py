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
    "wetter",
    "unwetter",
    "frost",
    "glaette",
    "gl\u00e4tte",
    "schnee",
    "regen",
    "sturm",
    "nebel",
    "temperatur",
    "dwd",
    "hitzewelle",
    "gewitter",
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
    "berlin-brandenburg",
    "mecklenburg-vorpommern",
    "niedersachsen-bremen",
    "rheinland-pfalz-saarland",
    "schleswig-holstein-hamburg",
    "bayern",
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
            "Use bold headings for: " + W_HEADS,
            "End with: " + SRC_WORD + " DWD / " + u + " and @HessenPersian.",
            "Return only Persian text. Title: " + t + " | Summary: " + s,
        ]
        return NL.join(parts)
    parts = [
        "Write a concise formal Persian Telegram news post.",
        "Line 1: bold headline. Next: 2 to 4 formal Persian bullet sentences starting with - .",
        "End with: " + SRC_WORD + " " + u + " and @HessenPersian.",
        "Return only Persian text. Title: " + t + " | Summary: " + s,
    ]
    return NL.join(parts)


def gen_post(item, force_weather=False):
    prompt = make_prompt(item, force_weather=force_weather)
    res = client.models.generate_content(model=MODEL_NAME, contents=prompt)
    return (res.text or "").strip()


def send_tg(text):
    url = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": False}
    raw = json.dumps(data).encode("utf-8")
    req = Request(url, data=raw, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=15) as resp:
        resp.read()


def main():
    t0 = time.time()
    posted = load_posted()
    items = []
    seen = set()

    for src in URLS:
        if time.time() - t0 > 35:
            break
        try:
            got = parse_items(fetch_text(src), src)
            log("OK " + src + " -> " + str(len(got)))
            for it in got:
                if it["link"] not in seen:
                    seen.add(it["link"])
                    items.append(it)
        except Exception as e:
            log("ERR " + src + " -> " + str(e))

    quota_hit = False
    w_done = 0
    w_tries = 0
    for it in items:
        if quota_hit or w_tries >= 1 or time.time() - t0 > 60:
            break
        u = it["link"]
        if not u or u in posted or not is_weather(it):
            continue
        w_tries += 1
        try:
            log("Weather: " + u)
            txt = gen_post(it, force_weather=True)
            if txt:
                send_tg(txt)
                save_posted(u)
                posted.add(u)
                w_done += 1
        except Exception as e:
            err_s = str(e)
            log("W_ERR " + u + " -> " + err_s)
            if "429" in err_s or "RESOURCE_EXHAUSTED" in err_s:
                quota_hit = True

    n_done = 0
    n_tries = 0
    for it in items:
        if quota_hit or n_tries >= 1 or n_done >= 1 or time.time() - t0 > 60:
            break
        u = it["link"]
        if not u or u in posted:
            continue
        n_tries += 1
        try:
            log("News: " + u)
            txt = gen_post(it, force_weather=False)
            if txt:
                send_tg(txt)
                save_posted(u)
                posted.add(u)
                n_done += 1
        except Exception as e:
            err_s = str(e)
            log("N_ERR " + u + " -> " + err_s)
            if "429" in err_s or "RESOURCE_EXHAUSTED" in err_s:
                quota_hit = True

    log("DONE weather=" + str(w_done) + " news=" + str(n_done) + " quota_hit=" + str(quota_hit))


if __name__ == "__main__":
    main()
