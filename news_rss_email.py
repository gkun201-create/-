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
        summary_raw = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
        summary_text = _clean_summary(summary_raw)

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
                "summary": summary_text,
                "source": source_title,
            }
        )
    return items


def _clean_summary(text: str) -> str:
    # Google News RSS summary는 HTML이 섞여올 수 있어 텍스트만 남깁니다.
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return " ".join(text.split()).strip()


def _is_ascii(s: str) -> bool:
    return all(ord(ch) < 128 for ch in (s or ""))


def _highlight_keyword(text: str, keyword: str) -> str:
    """
    HTML-safe 문자열을 반환하고, keyword 매칭 부분만 <strong> 처리합니다.
    (대소문자 구분이 애매한 영문 키워드는 IGNORECASE로 처리)
    """
    if not text:
        return ""
    if not keyword:
        return html.escape(text)

    flags = re.IGNORECASE if _is_ascii(keyword) else 0
    pattern = re.compile(re.escape(keyword), flags)

    out = []
    last = 0
    for m in pattern.finditer(text):
        out.append(html.escape(text[last : m.start()]))
        out.append("<strong>")
        out.append(html.escape(text[m.start() : m.end()]))
        out.append("</strong>")
        last = m.end()
    out.append(html.escape(text[last:]))
    return "".join(out)


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
    .summary { color: #222; font-size: 13px; margin-top: 6px; line-height: 1.4; }
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
            "<thead><tr><th>#</th><th>제목 / 요약</th><th>발행</th></tr></thead><tbody>"
        )
        for i, it in enumerate(items, 1):
            link_esc = html.escape(it["link"])
            pub_esc = html.escape(it.get("published", "") or "")
            src_esc = html.escape(it.get("source", "") or "")

            title_html = _highlight_keyword(it.get("title", "") or "", keyword)
            summary_html = _highlight_keyword(it.get("summary", "") or "", keyword) if it.get("summary") else ""

            title_cell = f'<a href="{link_esc}">{title_html}</a>'
            meta_bits = [b for b in [src_esc] if b]
            if meta_bits:
                title_cell += f'<div class="meta">{" · ".join(meta_bits)}</div>'
            if summary_html:
                title_cell += f'<div class="summary">{summary_html}</div>'

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
