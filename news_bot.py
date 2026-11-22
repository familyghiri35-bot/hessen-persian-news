import os
import feedparser
from google import genai
import requests

FEEDS = [
    "https://www.hessenschau.de/index.rss",
    "https://www.fr.de/rhein-main/rssfeed.rdf",
    "https://hessen.de/presse/rss",
]

CHANNEL_ID = "@HessenPersian"
STATE_FILE = "posted.txt"

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
bot_token = os.environ["TELEGRAM_BOT_TOKEN"]


def load_posted():
    if not os.path.exists(STATE_FILE):
        return set()
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def save_posted(posted_links):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        for link in list(posted_links)[-500:]:
            f.write(link + "\n")


def translate_and_summarize(title, summary, link):
    prompt = f"""تو سردبیر کانال تلگرام «نیازمندی‌ها و اخبار هسن» هستی. این خبر آلمانی را به فارسی روان، دقیق و رسمی برای ایرانیان مقیم ایالت هسن آلمان ترجمه و خلاصه کن.

قوانین فرمت:
- از علامت ستاره (*) یا مارک‌داون استفاده نکن.
- یک ایموجی مرتبط در ابتدای تیتر بگذار.
- متن خبر حداکثر ۳ تا ۴ خط کوتاه و کاربردی باشد.
- در انتها لینک منبع را قرار بده.

تیتر: {title}
خلاصه: {summary}
لینک: {link}"""

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt,
    )
    return response.text.strip()


def send_telegram(text):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "disable_web_page_preview": False,
    }
    resp = requests.post(url, json=payload, timeout=20)
    resp.raise_for_status()


def main():
    posted = load_posted()
    new_count = 0

    for feed_url in FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:3]:
            link = entry.get("link", "").strip()
            if not link or link in posted:
                continue

            title = entry.get("title", "")
            summary = entry.get("summary", "")

            try:
                persian_post = translate_and_summarize(title, summary, link)
                send_telegram(persian_post)
                posted.add(link)
                new_count += 1
                if new_count >= 3:
                    break
            except Exception as e:
                print(f"Error processing {link}: {e}")

        if new_count >= 3:
            break

    save_posted(posted)


if __name__ == "__main__":
    main()
