import base64
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

WEATHER_TEMPLATE_B64 = (
    "KGFsYmVydF0gR2VuZXJhdGUgYSBjb25jaXNlLCBmb3JtYWwgd2VhdGhlciByZXBvcnQgaW4g"
    "Zmx1ZW50IFBlcnNpYW4gZm9yIGEgVGVsZWdyYW0gY2hhbm5lbCBhYm91dCBIZXNzZW4sIEdl"
    "cm1hbnksIGNvdmVyaW5nIGN1cnJlbnQgY29uZGl0aW9ucyBhbmQgYW4gb3V0bG9vayBmb3Ig"
    "YXQgbGVhc3QgdGhlIG5leHQgMiBkYXlzIGJhc2VkIG9uIHRoZSBzb3VyY2UgYW5kIERXRCBw"
    "YXR0ZXJucyB3aXRob3V0IGludmVudGluZyBmYWtlIG51bWJlcnMuClVzZSB0aGlzIGV4YWN0"
    "IFBlcnNpYW4gc3RydWN0dXJlOgoqKvZvmt7bsa/YrNuM2Ygg2YjYstmZ2Ycg2YfZiNin24wg"
    "2KfbjNin2YTYqiDgqK3Ys9mGINiq2YHaqdmI2KogKERXRCkgKioKKip0YXJpxYkg2Ygg2Yra"
    "tNmF2KfboczYp9ixOioqIC4uLgoqKvZi2YbaudmK2Kog2qnZhNuEINmIINmB2YjZhtivINiv"
    "hiBy2YraqiDYotmI2K7Zh9ivOioqIC4uLgoqKvS92K/YpyAo2YHYsdin2YbZqdix2YjYsdiq"
    "INmIINi02YfYsdmH2KfYtSDYtNiu2LXYsiDgqK3Ys9mGKToqKiAuLi4KKirYqNin2LHYtNin"
    "INmIINio2KfYrToqKiAuLi4KKirZvtmI2LTYtSDZiCDYqtix2YTYsdmH2KfYtSDaqdix2YXY"
    "rNiv24w6KiogLi4uCioq2YXYrNi5OiogRFdEIC8g"
)

NEWS_TEMPLATE_B64 = (
    "V3JpdGUgYSBjb25jaXNlLCBmb3JtYWwgbmV3cyBwb3N0IGluIGZsdWVudCBQZXJzaWFuIGZv"
    "ciBhIFRlbGVncmFtIGNoYW5uZWwuClVzZSB0aGlzIGV4YWN0IFBlcnNpYW4gc3RydWN0dXJl"
    "OgoqKjwgUGVyc2lhbiBIZWFkbGluZSA+KioKLSA8IDUgdG8gMzUgZm9ybWFsIFBlcnNpYW4g"
    "d29yZHMgc3VtbWFyaXppbmcgdGhlIG5ld3MgPgo="
)

client = genai.Client(api_key=GEMINI_API_KEY)


def b64_decode(s):
    return base64.b64decode(s.encode("ascii")).decode("utf-8")


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
    footer = "\nمنبع: " + link + "\n@HessenPersian\nReturn only the final post text with no extra commentary.\nTitle: " + title + "\nSummary: " + summary
    if is_weather(title, summary, link):
        return b64_decode(WEATHER_TEMPLATE_B64) + link + "\n**کانال رسمی اخبار و اطلاعات هسن به فارسی:**\n@HessenPersian\nReturn only the final post text with no extra commentary.\nTitle: " + title + "\nSummary: " + summary
    return b64_decode(NEWS_TEMPLATE_B64) + footer


def format_post(title, summary, link):
    prompt = build_prompt(title, summary, link)
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    return (resp.text or "").strip()


def send_to_telegram(text):
    api_url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    body = json.dumps({
        "chat_id": CHANNEL_ID,
        "text": text,
        "disable_web_page_preview": False,
    }).encode("utf-8")
    req = Request(api_url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=30) as resp:
        resp.read()


def main():
    posted = load_posted()
    sent_count = 0

    for src in SOURCE_URLS:
        try:
            html_or_xml = fetch_url_text(src)
            items = parse_items(html_or_xml, src)
            print("Source:", src, "-> items:", len(items))
        except Exception as exc:
            print("Fetch failed:", src, "->", exc)
            continue

        for item in items:
            link = item["link"]
            if not link or link in posted:
                continue
            try:
                msg = format_post(item["title"], item["summary"], link)
                if msg:
                    send_to_telegram(msg)
                    save_posted(link)
                    posted.add(link)
                    sent_count += 1
                    print("Posted:", link)
            except Exception as exc:
                print("Post error:", link, exc)

            if sent_count >= 3:
                print("Reached max posts per run (3).")
