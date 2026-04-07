"""
뉴스/시장 정보 수집기
공개 RSS 피드와 KIS API 데이터를 조합하여 찌라시 생성 원재료를 수집합니다.
"""

import logging
import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import requests

from config import DB_PATH

logger = logging.getLogger(__name__)

# 공개 한국 경제 RSS 피드 (크롤링 없이 공개 피드만 사용)
RSS_FEEDS = [
    ("연합뉴스 경제", "https://www.yna.co.kr/rss/economy.xml"),
    ("연합뉴스 증권", "https://www.yna.co.kr/rss/stock.xml"),
    ("한국경제", "https://www.hankyung.com/feed/all-news"),
    ("매일경제", "https://www.mk.co.kr/rss/30100041/"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _init_briefing_db():
    """찌라시 DB 테이블 초기화"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_briefing (
            briefing_date TEXT PRIMARY KEY,
            content TEXT,
            raw_news TEXT,
            generated_at TEXT,
            confirmed INTEGER DEFAULT 0,
            confirmed_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def is_briefing_confirmed_today() -> bool:
    """오늘 찌라시를 이미 확인했는지 여부"""
    _init_briefing_db()
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT confirmed FROM daily_briefing WHERE briefing_date=?",
        (today,),
    )
    row = c.fetchone()
    conn.close()
    return bool(row and row[0])


def mark_briefing_confirmed():
    """오늘 찌라시 확인 완료 기록"""
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """INSERT OR REPLACE INTO daily_briefing
           (briefing_date, confirmed, confirmed_at)
           VALUES (?, 1, ?)
           ON CONFLICT(briefing_date) DO UPDATE SET confirmed=1, confirmed_at=?""",
        (today, datetime.now().isoformat(), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_cached_briefing_content() -> Optional[str]:
    """오늘 생성된 캐시된 찌라시 내용 반환"""
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT content FROM daily_briefing WHERE briefing_date=?", (today,))
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] else None


def save_briefing_content(content: str, raw_news: str = ""):
    """생성된 찌라시 내용을 DB에 저장"""
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """INSERT OR REPLACE INTO daily_briefing
           (briefing_date, content, raw_news, generated_at, confirmed)
           VALUES (?, ?, ?, ?, 0)""",
        (today, content, raw_news, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def fetch_rss_news(max_items: int = 30) -> list[dict]:
    """RSS 피드에서 최신 뉴스 수집"""
    news_items = []

    for source_name, url in RSS_FEEDS:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=8)
            resp.raise_for_status()

            # 간단한 RSS XML 파싱 (xml.etree 사용)
            import xml.etree.ElementTree as ET
            root = ET.fromstring(resp.content)

            # RSS 2.0 또는 Atom 형식 처리
            items = root.findall(".//item") or root.findall(
                ".//{http://www.w3.org/2005/Atom}entry"
            )

            for item in items[:8]:  # 소스당 최대 8개
                title = (
                    item.findtext("title")
                    or item.findtext("{http://www.w3.org/2005/Atom}title")
                    or ""
                ).strip()
                desc = (
                    item.findtext("description")
                    or item.findtext("{http://www.w3.org/2005/Atom}summary")
                    or ""
                ).strip()

                # HTML 태그 제거
                import re
                desc = re.sub(r"<[^>]+>", "", desc).strip()
                desc = desc[:200] if len(desc) > 200 else desc

                if title:
                    news_items.append({
                        "source": source_name,
                        "title": title,
                        "description": desc,
                    })

            logger.debug(f"RSS 수집 완료: {source_name} ({len(items)}건)")

        except Exception as e:
            logger.warning(f"RSS 수집 실패 [{source_name}]: {e}")
            continue

    return news_items[:max_items]


def fetch_kis_market_summary() -> dict:
    """KIS API로 전일/현재 시장 요약 데이터 수집"""
    summary = {}
    try:
        from kis.kis_client import get_client
        client = get_client()

        # 거래량 상위 5개 종목
        top_vol = client.get_volume_ranking(top_n=5)
        summary["volume_top"] = [
            f"{s['name']}({s['code']}) {s['change_rate']:+.1f}%"
            for s in top_vol
        ]

        # 등락률 상위 5개
        top_rise = client.get_price_ranking("rise", top_n=5)
        summary["rise_top"] = [
            f"{s['name']} {s['change_rate']:+.1f}%"
            for s in top_rise
        ]

        # 하락률 상위 5개
        top_fall = client.get_price_ranking("fall", top_n=5)
        summary["fall_top"] = [
            f"{s['name']} {s['change_rate']:+.1f}%"
            for s in top_fall
        ]

        logger.info("KIS 시장 요약 데이터 수집 완료")

    except Exception as e:
        logger.warning(f"KIS 시장 요약 수집 실패: {e}")

    return summary


def collect_all_market_info() -> tuple[list[dict], dict]:
    """
    뉴스 + 시장 데이터를 종합 수집합니다.

    Returns:
        (news_items, market_summary)
    """
    logger.info("아침 시장 정보 수집 시작...")
    news = fetch_rss_news(max_items=30)
    market = fetch_kis_market_summary()
    logger.info(f"수집 완료: 뉴스 {len(news)}건, 시장 데이터 {len(market)}개 항목")
    return news, market
