import html
import os
import ssl
import smtplib
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from time import mktime
from urllib.parse import quote

import feedparser

# 1. 뉴스 검색 URL 생성 (키워드에 'world news'와 'when:24h'를 조합)
def google_news_rss_url(keyword: str, hl="ko", gl="KR", ceid="KR:ko") -> str:
    # 24시간 내의 뉴스를 가져오기 위해 검색어 뒤에 when:24h를 붙입니다.
    query = f"{keyword} when:24h"
    q = quote(query)
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
            
        # 발행 시간 확인 및 24시간 필터링
        if getattr(entry, "published_parsed", None):
            pub_dt = datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
            if pub_dt < cutoff:
                continue

        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        
        # 언론사 정보 가져오기
        source_title = ""
        try:
            source_title = getattr(getattr(entry, "source", None), "title", "") or ""
        except Exception:
            source_title = ""

        items.append({
            "title": title,
            "link": link,
            "source": source_title,
        })
    return items

# 2. 이메일 본문 생성 (볼드 처리 및 요약 삭제)
def build_email_body(results: dict) -> str:
    style = """
    <style>
    body { font-family: 'Malgun Gothic', sans-serif; line-height: 1.6; }
    h2 { color: #202124; border-bottom: 2px solid #4285f4; padding-bottom: 10px; }
    table { border-collapse: collapse; width: 100%; margin-bottom: 20px; }
    th, td { border: 1px solid #e0e0e0; padding: 12px; text-align: left; }
    th { background: #f8f9fa; font-weight: bold; color: #5f6368; }
    a { color: #1a73e8; text-decoration: none; font-weight: 500; }
    .meta { color: #70757a; font-size: 12px; margin-top: 4px; }
    </style>
    """
    parts = [f"<html><head>{style}</head><body>", "<h2>최신 전 세계 주요 뉴스 (24시간 이내)</h2>"]
    
    for keyword, items in results.items():
        if not items:
            parts.append(f"<p>'{keyword}'에 대한 최근 24시간 내 뉴스가 없습니다.</p>")
            continue
            
        parts.append("<table><thead><tr><th>#</th><th>뉴스 제목 및 링크</th></tr></thead><tbody>")
        
        for i, it in enumerate(items, 1):
            title_esc = html.escape(it["title"])
            link_esc = html.escape(it["link"])
            src_esc = html.escape(it["source"])

            # 요약과 볼드 처리 없이 깔끔하게 제목과 링크만 구성
            title_cell = f'<a href="{link_esc}">{title_esc}</a>'
            if src_esc:
                title_cell += f'<div class="meta">출처: {src_esc}</div>'

            parts.append(f"<tr><td style='width:30px; text-align:center;'>{i}</td><td>{title_cell}</td></tr>")
        
        parts.append("</tbody></table>")
    
    parts.append("</body></html>")
    return "".join(parts)

def send_gmail(to_email: str, subject: str, body: str):
    # 환경 변수에서 메일 설정 정보를 가져옵니다.
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

def main():
    # 키워드를 '전세계 주요 뉴스'로 고정하거나 기존 파일을 읽도록 설정
    # 여기서는 'World News'를 키워드로 하여 전 세계 뉴스를 가져옵니다.
    keywords = ["World News"] 
    
    results = {kw: fetch_news(kw, limit=10) for kw in keywords}

    body = build_email_body(results)
    
    # 환경 변수 설정에 따라 본인에게 메일 발송
    try:
        to_email = os.environ.get("GMAIL_TO", os.environ["GMAIL_USER"])
        subject = f"[Daily Brief] 전 세계 주요 뉴스 10선 ({datetime.now().strftime('%Y-%m-%d')})"
        send_gmail(to_email=to_email, subject=subject, body=body)
        print("메일 전송이 완료되었습니다.")
    except KeyError:
        print("오류: 환경 변수(GMAIL_USER, GMAIL_APP_PASSWORD)를 확인해주세요.")

if __name__ == "__main__":
    main()
