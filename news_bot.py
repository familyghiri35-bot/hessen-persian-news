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
    "https://www.hessenschau.de/index~rss.xml",
    "https://www.hessenschau.de/aktuelles/index.html",
    "https://www.fr.de/hessen/index.rss",
    "https://www.fr.de/hessen/",
    "https://www.hessen.de/rss.xml",
    "https://www.hessen.de/presse",
    "https://www.dwd.de/DE/wetter/wetterundklima_vorort/hessen/hessen_node.html",
]

W_KEYS = [
    "wetter", "unwetter", "frost", "glaette", "glätte",
    "schnee", "regen", "sturm", "nebel", "temperatur",
    "dwd", "hitzewelle", "gewitter",
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
    for m in re.finditer(r"<item\b[^>]*>(.*?)</item>", html, re.I | re.S):
        blk = m.group(1)
        tm = re.search(r"<title>(.*?)</title>", blk, re.I | re.S)
        lm = re.search(r"<link>(.*?)</link>", blk, re.I | re.S)
        if tm and lm:
            t = clean_html(tm.group(1))
            u = unescape(re.sub(r"<[^>]+>", "", lm.group(1))).strip()
            if t and u.startswith("http") and u not in seen:
                seen.add(u)
                out.append({"title": t, "summary": t, "link": u})
    if out:
        return out
    for m in re.finditer(r"<a\b[^>]*>(.*?)</a>", html, re.I | re.S):
        head = html[m.start():m.start() + 250]
        hm = re.search(r"href=[\x27\x22]([^\x27\x22]+)[\x27\x22]", head, re.I)
        if not hm:
            continue
        t = clean_html(m.group(1))
        u = urljoin(base, hm.group(1).strip())
        if len(t) < 25 or not u.startswith("https://"):
            continue
        if any(x in u for x in ["#", "/suche", "/kontakt", "/impressum", "/datenschutz", "login"]):
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
            "Use bold headings for: پیش‌بینی وضع هوای ایالت هسن (DWD), وضعیت فعلی و چشم‌انداز دو روز آینده، دما (فرانکفورت و هسن)، بارش و باد، توصیه و پوشش.",
            "End with: منبع: DWD / " + u + " and @HessenPersian.",
            "Return only Persian text. Title: " + t + " | Summary: " + s,
        ]
        return NL.join(parts)
    parts = [
        "Write a concise formal Persian Telegram news post.",
        "Line 1: bold headline. Next: 2 to 4 formal Persian bullet sentences starting with - .",
        "End with: منبع: " + u + " and @HessenPersian.",
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
        if time.time() - t0 > 45:
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

    w_done = 0
    for it in items:
        if time.time() - t0 > 75:
            break
        u = it["link"]
        if not u or u in posted or not is_weather(it):
            continue
        try:
            log("Weather: " + u)
            txt = gen_post(it, force_weather=True)
            if txt:
                send_tg(txt)
                save_posted(u)
                posted.add(u)
                w_done += 1
                break
        except Exception as e:
            log("W_ERR " + u + " -> " + str(e))

    n_done = 0
    for it in items:
        if time.time() - t0 > 75 or n_done >= 1:
            break
        u = it["link"]
        if not u or u in posted:
            continue
        try:
            log("News: " + u)
            txt = gen_post(it, force_weather=False)
            if txt:
                send_tg(txt)
                save_posted(u)
                posted.add(u)
                n_done += 1
        except Exception as e:
            log("N_ERR " + u + " -> " + str(e))

    log("DONE weather=" + str(w_done) + " news=" + str(n_done))


if __name__ == "__main__":
    main()
