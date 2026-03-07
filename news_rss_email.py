import os
import ssl
import smtplib
from email.mime.text import MIMEText
from urllib.parse import quote

import feedparser


def google_news_rss_url(keyword: str, hl="ko", gl="KR", ceid="KR:ko") -> str:
    q = quote(keyword)
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"


def fetch_news(keyword: str, limit: int = 10):
    url = google_news_rss_url(keyword)
    feed = feedparser.parse(url)

    items = []
    for entry in feed.entries[:limit]:
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        published = getattr(entry, "published", "").strip()
        items.append({"title": title, "link": link, "published": published})
    return items


def build_email_body(results: dict) -> str:
    lines = []
    lines.append("Google 뉴스 RSS 요약\n")
    for keyword, items in results.items():
        lines.append(f"[{keyword}] ({len(items)}개)\n")
        if not items:
            lines.append("- 결과 없음\n")
        for i, it in enumerate(items, 1):
            pub = f" ({it['published']})" if it["published"] else ""
            lines.append(f"{i}. {it['title']}{pub}\n   {it['link']}\n")
        lines.append("\n")
    return "".join(lines)


def send_gmail(to_email: str, subject: str, body: str):
    gmail_user = os.environ["GMAIL_USER"]
    gmail_app_password = os.environ["GMAIL_APP_PASSWORD"]

    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = to_email

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(gmail_user, gmail_app_password)
        server.sendmail(gmail_user, [to_email], msg.as_string())


def load_keywords(path: str = "keywords.txt"):
    keywords = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            kw = line.strip()
            if not kw or kw.startswith("#"):
                continue
            keywords.append(kw)
    return keywords


def main():
    keywords = load_keywords("keywords.txt")
    results = {kw: fetch_news(kw, limit=10) for kw in keywords}

    body = build_email_body(results)
    print(body)

    to_email = os.environ.get("GMAIL_TO", os.environ["GMAIL_USER"])
    send_gmail(to_email=to_email, subject=f"Google 뉴스 RSS: {', '.join(keywords)}", body=body)
    print("메일 전송 완료")


if __name__ == "__main__":
    main()
