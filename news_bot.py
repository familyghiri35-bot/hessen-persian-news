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
    "morgen",
    "ausblick",
]

WEATHER_TEMPLATE_B64 = (
    "R2VuZXJhdGUgYSBjb25jaXNlLCBmb3JtYWwgd2VhdGhlciByZXBvcnQgaW4gZmx1ZW50IFBl"
    "cnNpYW4gZm9yIGEgVGVsZWdyYW0gY2hhbm5lbCBhYm91dCBIZXNzZW4sIEdlcm1hbnksIGZv"
    "Y3VzaW5nIG9uIHRvbW9ycm93IGFuZCB0aGUgbmV4dCAyIGRheXMgb3V0bG9vayBiYXNlZCBv"
    "biB0aGUgc291cmNlIGFuZCBEV0QgcGF0dGVybnMgd2l0aG91dCBpbnZlbnRpbmcgZmFrZSBu"
    "dW1iZXJzLgpVc2UgdGhpcyBleGFjdCBQZXJzaWFuIHN0cnVjdHVyZToKKirZvmt7bsa/YrNu"
    "M2Ygg2YjYstmZ2Ycg2YfZiNin24wg2KfbjNin2YTYqiDgqK3Ys9mGINiq2YHaqdmI2KogKERX"
    "RCkgKioKKip0YXJpxYkg2Ygg2YratNmF2KfboczYp9ixOioqIC4uLgoqKvZi2YbaudmK2Kog"
    "2qnZhNuEINmIINmB2YjZhtivINivhiBy2YraqiDYotmI2K7Zh9ivOioqIC4uLgoqKvS92K/Y"
    "pyAo2YHYsdin2YbZqdix2YjYsdiqINmIINi02YfYsdmH2KfYtSDYtNiu2LXYsiDgqK3Ys9mG"
    "KToqKiAuLi4KKirYqNin2LHYtNinINmIINio2KfYrToqKiAuLi4KKirZvtmI2LTYtSDZiCDY"
    "qtix2YTYsdmH2KfYtSDaqdix2YXYrNiv24w6KiogLi4uCioq2YXYrNi5OiogRFdEIC8g"
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
    return any(w in text for w in ["wetter", "unwetter", "frost", "glaette", "glätte", "schnee", "regen", "sturm", "nebel", "temperatur", "dwd", "hitzewelle", "gewitter"])


def build_prompt(title, summary, link, force_weather=False):
    footer = "\nمنبع: " + link + "\n@HessenPersian\nReturn only the final post text with no extra commentary.\nTitle: " + title + "\nSummary: " + summary
    if force_weather or is_weather(title, summary, link):
        return b64_decode(WEATHER_TEMPLATE_B64) + link + "\n**کانال رسمی اخبار و اطلاعات هسن به فارسی:**\n@HessenPersian\nReturn only the final post text with no extra commentary.\nTitle: " + title + "\nSummary: " + summary
    return b64_decode(NEWS_TEMPLATE_B64) + footer


def format_post(title, summary, link, force_weather=False):
    prompt = build_prompt(title, summary, link, force_weather=force_weather)
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
    all_items = []
    seen_links = set()

    for src in SOURCE_URLS:
        try:
            html_or_xml = fetch_url_text(src)
            items = parse_items(html_or_xml, src)
            print("Source:", src, "-> items:", len(items))
            for it in items:
                if it["link"] not in seen_links:
                    seen_links.add(it["link"])
                    all_items.append(it)
        except Exception as exc:
            print("Fetch failed:", src, "->", exc)

    weather_sent = 0
    for item in all_items:
        link = item["link"]
        if not link or link in posted or not is_weather(item["title"], item["summary"], link):
            continue
        try:
            msg = format_post(item["title"], item["summary"], link, force_weather=True)
            if msg:
                send_to_telegram(msg)
                save_posted(link)
                posted.add(link)
                weather_sent += 1
                print("Posted weather:", link)
                break
        except Exception as exc:
            print("Weather post error:", link, exc)

    news_sent = 0
    for item in all_items:
        link = item["link"]
        if not link or link in posted:
            continue
        try:
            msg = format_post(item["title"], item["summary"], link, force_weather=False)
            if msg:
                send_to_telegram(msg)
                save_posted(link)
                posted.add(link)
                news_sent += 1
                print("Posted news:", link)
        except Exception as exc:
            print("News post error:", link, exc)

        if news_sent >= 2:
            break

    print("Done. Weather sent:", weather_sent, "| News sent:", news_sent)


if __name__ == "__main__":
    main()
