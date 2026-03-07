import html
import os
import re
import ssl
import smtplib
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from time import mktime
from urllib.parse import quote

import feedparser


def google_news_rss_url(keyword: str, hl="ko", gl="KR", ceid="KR:ko") -> str:
    # 24시간 이내 검색을 위해 키워드에 when:24h를 붙입니다.
    q = quote(f"{keyword} when:24h")
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
        
        # 24시간 이내 뉴스인지 확인
        if getattr(entry, "published_parsed", None):
            pub_dt = datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
            if pub_dt < cutoff:
                continue
                
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        published_str = getattr(entry, "published", "").strip()

        source_title = ""
        try:
            source_title = getattr(getattr(entry, "source", None), "title", "") or ""
        except Exception:
            source_title = ""

        items.append(
            {
                "title": title,
                "link": link,
                "published": published_str,
                "source": source_title,
            }
        )
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
    .meta { color: #666; font-size: 12px; margin-top: 4px; }
    </style>
    """
    parts = [f"<html><head>{style}</head><body>", "<h2>설정 키워드 뉴스 브리핑 (최근 24시간)</h2>"]
    for keyword, items in results.items():
        parts.append(f"<h3>[{html.escape(keyword)}] ({len(items)}개)</h3>")
        if not items:
            parts.append("<p>최근 24시간 내 결과 없음</p>")
            continue
        parts.append(
            "<table>"
            "<thead><tr><th>#</th><th>제목</th><th>발행</th></tr></thead><tbody>"
        )
        for i, it in enumerate(items, 1):
            link_esc = html.escape(it["link"])
            pub_esc = html.escape(it.get("published", "") or "")
            src_esc = html.escape(it.get("source", "") or "")
            title_esc = html.escape(it.get("title", "") or "")

            # 볼드 처리와 요약 없이 제목만 깔끔하게 구성
            title_cell = f'<a href="{link_esc}">{title_esc}</a>'
            if src_esc:
                title_cell += f'<div class="meta">{src_esc}</div>'

            parts.append(
                f"<tr><td>{i}</td><td>{title_cell}</td><td>{pub_esc}</td></tr>"
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
    # 파일이 없을 경우를 대비한 기본값 설정
    if not os.path.exists(path):
        return ["인공지능", "경제"] 
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            kw = line.strip()
            if not kw or kw.startswith("#"):
                continue
            keywords.append(kw)
    return keywords


def main():
    # 1. keywords.txt에서 키워드 로드
    keywords = load_keywords("keywords.txt")
    
    # 2. 각 키워드별 뉴스 수집 (24시간 이내)
    results = {kw: fetch_news(kw, limit=10) for kw in keywords}

    # 3. 이메일 본문 생성 (요약/볼드 제거됨)
    body = build_email_body(results)
    print("이메일 본문 생성 완료")

    # 4. 메일 발송
    try:
        to_email = os.environ.get("GMAIL_TO", os.environ["GMAIL_USER"])
        subject = f"데일리 뉴스 리포트: {', '.join(keywords)}"
        send_gmail(to_email=to_email, subject=subject, body=body)
        print("메일 전송 완료")
    except Exception as e:
        print(f"메일 전송 중 오류 발생: {e}")


if __name__ == "__main__":
    main()
