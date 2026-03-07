import html
import os
import ssl
import smtplib
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from time import mktime
from urllib.parse import quote

import feedparser


def google_news_rss_url(keyword: str, hl="ko", gl="KR", ceid="KR:ko") -> str:
    q = quote(keyword)
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"


def fetch_news(keyword: str, limit: int = 10, within_hours: int = 24):
    url = google_news_rss_url(keyword)
    feed = feedparser.parse(url)

    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(hours=within_hours)
    items = []
    for entry in feed.entries:
        if len(items) >= limit:
            break
        published_str = getattr(entry, "published", "").strip()
        # 24시간 이내인지 확인 (published_parsed가 있으면)
        if getattr(entry, "published_parsed", None):
            pub_dt = datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
            if pub_dt < cutoff:
                continue
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        items.append({"title": title, "link": link, "published": published_str})
    return items


def build_email_body(results: dict) -> str:
    style = """
    <style>
    body { font-family: Malgun Gothic, sans-serif; }
    h2 { color: #333; }
    h3 { color: #555; margin-top: 1.2em; }
    table { border-collapse: collapse; width: 100%; margin-bottom: 1.5em; }
    th, td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; }
    th { background: #f5f5f5; font-weight: bold; }
    tr:nth-child(even) { background: #fafafa; }
    a { color: #1967d2; text-decoration: none; }
    a:hover { text-decoration: underline; }
    </style>
    """
    parts = [f"<html><head>{style}</head><body>", "<h2>Google 뉴스 RSS 요약</h2>"]
    for keyword, items in results.items():
        parts.append(f"<h3>[{html.escape(keyword)}] ({len(items)}개)</h3>")
        if not items:
            parts.append("<p>결과 없음</p>")
            continue
        parts.append(
            "<table>"
            "<thead><tr><th>#</th><th>제목</th><th>발행일</th></tr></thead><tbody>"
        )
        for i, it in enumerate(items, 1):
            title_esc = html.escape(it["title"])
            link_esc = html.escape(it["link"])
            pub_esc = html.escape(it["published"]) if it["published"] else ""
            parts.append(
                f'<tr><td>{i}</td><td><a href="{link_esc}">{title_esc}</a></td><td>{pub_esc}</td></tr>'
            )
        parts.append("</tbody></table>")
    parts.append("</body></html>")
    return "".join(parts)


def send_gmail(to_email: str, subject: str, body: str):
    gmail_user = os.environ["GMAIL_USER"]
    gmail_app_password = os.environ["GMAIL_APP_PASSWORD"]

    msg = MIMEText(body, "html", "utf-8")
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
