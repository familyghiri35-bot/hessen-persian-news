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
    "wetter", "unwetter", "frost", "glätte", "schnee", "regen",
    "sturm", "nebel", "temperatur", "dwd", "hitzewelle", "gewitter"
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
        prompt = f"""
یک گزارش هواشناسی کوتاه، دقیق و رسمی برای کانال تلگرام بنویس که وضعیت فعلی و چشم‌انداز دست‌کم دو روز آینده ایالت هسن آلمان را پوشش دهد.
از اطلاعات زیر استفاده کن (و اگر بازه دو روز آینده در متن منبع نبود، به‌طور شفاف به وضعیت گزارش‌شده و چشم‌انداز دو روز آینده بر اساس الگوهای هواشناسی هسن و DWD اشاره کن بدون اینکه عدد دمای جعلی بسازی):

عنوان منبع: {title}
خلاصه منبع: {summary}
لینک منبع: {link}

قالب خروجی را دقیقاً به این شکل و به زبان فارسی روان بنویس:
🌫 **پیش‌بینی وضع هوای ایالت هسن (گزارش DWD)**
📅 **تاریخ و چشم‌انداز:** وضعیت فعلی و پیش‌بینی حداقل تا دو روز آینده

🌤 **وضعیت کلی و روند دو روز آینده:** ...
🌡 **دما (فرانکفورت و شهرهای شاخص هسن):** ...
🌧 **بارش و باد:** ...
🧥 **پوشش و توصیه‌های کاربردی:** ...

📌 **منبع:** DWD / {link}

📢 **کانال رسمی اخبار و اطلاعات هسن به فارسی:**
👉 @HessenPersian

فقط متن نهایی پست را برگردان و هیچ توضیح اضافه‌ای ننویس.
"""
    else:
        prompt = f"""
یک خبر کوتاه، شفاف، رسمی و دقیق به زبان فارسی برای کانال تلگرام بنویس.
از اطلاعات زیر استفاده کن:

عنوان: {title}
خلاصه: {summary}
لینک: {link}

قالب خروجی را دقیقاً به این شکل بنویس:
📰 **عنوان خبر به فارسی**

▫️ خلاصه کوتاه و دقیق خبر در ۲ تا ۴ جمله روان و رسمی.

🔗 منبع: {link}
👉 @HessenPersian

فقط
