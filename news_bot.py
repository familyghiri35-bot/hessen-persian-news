import os
import re
import feedparser
import requests
from google import genai

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
CHANNEL_ID = "@HessenPersian"
POSTED_FILE = "posted.txt"

RSS_FEEDS = [
    "https://www.hessenschau.de/index~rss.xml",
    "https://www.fr.de/hessen/index.rss",
    "https://www.hessen.de/rss.xml",
]

WEATHER_KEYWORDS = [
    "wetter",
    "unwetter",
    "frost",
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


def load_posted_links() -> set[str]:
    if not os.path.exists(POSTED_FILE):
        return set()
    with open(POSTED_FILE, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def save_posted_link(link: str) -> None:
    with open(POSTED_FILE, "a", encoding="utf-8") as f:
        f.write(link + "\n")


def is_weather_item(title: str, summary: str, link: str) -> bool:
    combined = f"{title} {summary} {link}".lower()
    return any(re.search(rf"\b{re.escape(kw)}", combined) for kw in WEATHER_KEYWORDS)


def format_post_with_gemini(title: str, summary: str, link: str) -> str:
    if is_weather_item(title, summary, link):
        prompt = (
            "یک گزارش هواشناسی کوتاه، دقیق و رسمی برای کانال تلگرام بنویس که وضعیت فعلی و چشم‌انداز دست‌کم دو روز آینده ایالت هسن آلمان را پوشش دهد.\n"
            "از اطلاعات زیر استفاده کن (و اگر بازه دو روز آینده در متن منبع نبود، به‌طور شفاف به وضعیت گزارش‌شده و چشم‌انداز دو روز آینده بر اساس الگوهای هواشناسی هسن و DWD اشاره کن بدون اینکه عدد دمای جعلی بسازی):\n\n"
            f"عنوان منبع: {title}\n"
            f"خلاصه منبع: {summary}\n"
            f"لینک منبع: {link}\n\n"
            "قالب خروجی را دقیقاً به این شکل و به زبان فارسی روان بنویس:\n"
            "🌫 **پیش‌بینی وضع هوای ایالت هسن (گزارش DWD)**\n"
            "📅 **تاریخ و چشم‌انداز:** وضعیت فعلی و پیش‌بینی حداقل تا دو روز آینده\n\n"
            "🌤 **وضعیت کلی و روند دو روز آینده:** ...\n"
            "🌡 **دما (فرانکفورت و شهرهای شاخص هسن):** ...\n"
            "🌧 **بارش و باد:** ...\n"
            "🧥 **پوشش و توصیه‌های کاربردی:** ...\n\n"
            f"📌 **منبع:** DWD / {link}\n\n"
            "📢 **کانال رسمی اخبار و اطلاعات هسن به فارسی:**\n"
            "👉 @HessenPersian\n\n"
            "فقط متن نهایی پست را برگردان و هیچ توضیح اضافه‌ای ننویس."
        )
    else:
        prompt = (
            "یک خبر کوتاه، شفاف، رسمی و دقیق به زبان فارسی برای کانال تلگرام بنویس.\n"
            "از اطلاعات زیر استفاده کن:\n\n"
            f"عنوان: {title}\n"
            f"خلاصه: {summary}\n"
            f"لینک: {link}\n\n"
            "قالب خروجی را دقیقاً به این شکل بنویس:\n"
            "📰 **عنوان خبر به فارسی**\n\n"
            "▫️ خلاصه کوتاه و دقیق خبر در ۲ تا ۴ جمله روان و رسمی.\n\n"
            f"🔗 منبع: {link}\n"
            "👉 @HessenPersian\n\n"
            "فقط متن نهایی پست را برگردان و هیچ توضیح اضافه‌ای ننویس."
        )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    return (response.text or "").strip()


def send_telegram_message(text: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,
    }
    resp = requests.post(url, json=payload, timeout=30)
    if not resp.ok:
        payload.pop("parse_mode", None)
        resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()


def main() -> None:
    posted = load_posted_links()
    new_count = 0

    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        entries = getattr(feed, "entries", [])
        print(f"Checking feed {feed_url} -> {len(entries)} items")

        for entry in entries:
            link = getattr(entry, "link", "").strip()
            if not link or link in posted:
                continue

            title = getattr(entry, "title", "").strip()
            summary = getattr(entry, "summary", "").strip()

            try:
                post_text = format_post_with_gemini(title, summary, link)
                if post_text:
                    send_telegram_message(post_text)
                    save_posted_link(link)
                    posted.add(link)
                    new_count += 1
                    print(f"Posted: {link}")
            except Exception as exc:
                print(f"Error processing {link}: {exc}")

            if new_count >= 3:
                print("Reached max new posts per run (3). Stopping.")
                return

    print(f"Done. Total new posts sent: {new_count
