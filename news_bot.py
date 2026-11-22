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
    "wetter", "unwetter", "frost", "glaette", "glätte",
    "schnee", "regen", "sturm", "nebel", "temperatur",
    "dwd", "hitzewelle", "gewitter",
]

client = genai.Client(api_key=GEMINI_API_KEY)


def load_posted():
    if not os.path.exists(POSTED_FILE):
        return set()
    with open(POSTED_FILE, "r", encoding="utf-8") as f:
        return {x.strip() for x in f.read().splitlines() if x.strip()}


def save_posted(link):
    with open(POSTED_FILE, "a", encoding="utf-8") as f:
        f.write(link + "\n")


def fetch_url_text(url):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    req = Request(url, headers=headers)
    with urlopen(req, timeout=20) as resp:
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
        return (
            "Write a concise formal Persian weather forecast for Hessen, Germany "
            "covering current conditions, tomorrow, and the next 2 days based on the source and DWD patterns "
            "without inventing fake temperatures.\n"
            "Use bold Persian headings for: پیش‌بینی وضع هوای ایالت هسن (DWD), "
            "وضعیت فعلی و چشم‌انداز دو روز آینده، دما (فرانکفورت و هسن)، بارش و باد، توصیه و پوشش.\n"
            "End with:\nمنبع: DWD / " + link + "\n@HessenPersian\n"
            "Return only the final Persian text.\nTitle: " + title + "\nSummary: " + summary
        )
    return (
        "Write a concise formal Persian Telegram news post with a bold headline on line 1, "
        "then 2 to 4 formal Persian summary sentences starting with '- ', "
        "then 'منبع: " + link + "' and '@HessenPersian'.\n"
        "Return only the final Persian text.\nTitle: " + title + "\nSummary: " + summary
    )


def format_post(title, summary, link, force_weather=False):
    prompt = build_prompt(title, summary, link, force_weather=force_weather)
    resp = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    return (resp.text or "").strip()


def send_to_telegram(text):
    api_url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    payload = {"chat_id": CHANNEL_ID, "text": text, "disable_web_page_preview": False}
    body = json.dumps(payload).encode("utf-8")
    req = Request(api_url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=30) as resp:
        resp.read()


def main():
    posted = load_posted()
    all_items = []
    seen_links = set()
    for src in SOURCE_URLS:
        try:
            items = parse_items(fetch_url_text(src), src)
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
