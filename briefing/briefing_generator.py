"""
찌라시(투자 정보지) 생성기
수집된 뉴스와 시장 데이터를 AI로 분석하여
상위 투자자 스타일의 아침 정보지를 생성합니다.
"""

import json
import logging
from datetime import datetime, date

from briefing.news_fetcher import (
    collect_all_market_info,
    get_cached_briefing_content,
    save_briefing_content,
)
from ai.providers import get_ai_manager
from youtube.principle_extractor import load_principles_from_db

logger = logging.getLogger(__name__)

BRIEFING_SYSTEM_PROMPT = """당신은 기관 투자자와 헤지펀드 매니저들이 아침마다 받아보는
프리미엄 투자 정보지 작성 전문가입니다.

일반 투자자는 절대 접하기 어려운 상위 0.1% 투자자 시각의 날카로운 분석을
마치 '찌라시(기관 내부 정보지)' 형태로 작성합니다.

형식:
- 선정적이지 않되 임팩트 있는 표현
- 구체적 종목 언급 (단, 추천이 아닌 분석)
- 기관/외국인 수급 시각
- 숫자와 근거 기반
- 경제 신문보다 훨씬 솔직하고 직접적인 표현

반드시 다음 HTML 형식으로 출력하세요 (PyQt5 QTextBrowser에서 렌더링):
<html>
<body style="font-family: '맑은 고딕', Arial; background: #1a1a1a; color: #e8e8e8; padding: 20px;">
  [내용]
</body>
</html>"""

BRIEFING_USER_PROMPT = """오늘 날짜: {today}
현재 시각: {time}

=== 수집된 경제 뉴스 ===
{news_text}

=== KIS 시장 데이터 ===
{market_text}

=== 투자 원칙 컨텍스트 ===
{principles_text}

위 정보를 종합하여, 오늘 아침 상위 투자자들이 주목해야 할
투자 정보지(찌라시)를 HTML 형식으로 작성하세요.

필수 포함 항목:
1. 【오늘의 핵심 시그널】 - 가장 중요한 1-2가지 투자 포인트
2. 【기관/외국인 동향】 - 수급 분석 (추정 포함)
3. 【주목 섹터/종목】 - 구체적 언급 3-5개
4. 【리스크 경보】 - 오늘 조심해야 할 것
5. 【오늘의 전략】 - 투자 원칙 기반 오늘의 접근법

스타일: 기관 내부 정보지처럼 직접적이고 솔직하게. 일반 신문 기사 스타일 절대 금지."""


def _format_news_for_prompt(news_items: list[dict]) -> str:
    if not news_items:
        return "(뉴스 수집 실패 - AI 자체 분석으로 대체)"
    lines = []
    for i, item in enumerate(news_items[:20], 1):
        lines.append(f"{i}. [{item['source']}] {item['title']}")
        if item.get("description"):
            lines.append(f"   {item['description'][:100]}")
    return "\n".join(lines)


def _format_market_for_prompt(market: dict) -> str:
    if not market:
        return "(시장 데이터 수집 실패)"
    lines = []
    if market.get("volume_top"):
        lines.append("거래량 상위: " + " / ".join(market["volume_top"]))
    if market.get("rise_top"):
        lines.append("상승 상위: " + " / ".join(market["rise_top"]))
    if market.get("fall_top"):
        lines.append("하락 상위: " + " / ".join(market["fall_top"]))
    return "\n".join(lines) if lines else "(시장 데이터 없음)"


def _format_principles_for_prompt() -> str:
    principles = load_principles_from_db()
    if not principles:
        return "(투자 원칙 미설정 - 채널 분석 후 반영됩니다)"
    lines = [f"- [{p['category']}] {p['title']}: {p['description']}" for p in principles[:5]]
    return "\n".join(lines)


def generate_morning_briefing(force_regenerate: bool = False) -> str:
    """
    아침 투자 정보지를 생성합니다.
    당일 캐시가 있으면 캐시를 반환합니다.

    Args:
        force_regenerate: True면 캐시 무시하고 재생성

    Returns:
        HTML 형식의 찌라시 내용
    """
    # 캐시 확인
    if not force_regenerate:
        cached = get_cached_briefing_content()
        if cached:
            logger.info("캐시된 아침 정보지 반환")
            return cached

    logger.info("아침 투자 정보지 생성 시작...")

    # 데이터 수집
    news_items, market_summary = collect_all_market_info()

    now = datetime.now()
    today_str = now.strftime("%Y년 %m월 %d일 (%a)")
    time_str = now.strftime("%H:%M")

    prompt = BRIEFING_USER_PROMPT.format(
        today=today_str,
        time=time_str,
        news_text=_format_news_for_prompt(news_items),
        market_text=_format_market_for_prompt(market_summary),
        principles_text=_format_principles_for_prompt(),
    )

    # AI 생성
    try:
        manager = get_ai_manager()
        if manager.is_ready():
            content = manager.chat_analysis(BRIEFING_SYSTEM_PROMPT, prompt, max_tokens=3000)
        else:
            # AI 미설정 시 기본 템플릿
            content = _fallback_briefing(today_str, news_items, market_summary)
    except Exception as e:
        logger.error(f"AI 찌라시 생성 실패: {e}")
        content = _fallback_briefing(today_str, news_items, market_summary)

    # DB 저장
    raw_news_json = str([f"[{n['source']}] {n['title']}" for n in news_items])
    save_briefing_content(content, raw_news_json)
    logger.info("아침 투자 정보지 생성 완료")

    return content


def _fallback_briefing(today_str: str, news_items: list, market: dict) -> str:
    """AI 미설정 시 기본 HTML 정보지"""
    news_html = ""
    for item in news_items[:10]:
        news_html += f"<li><b>[{item['source']}]</b> {item['title']}</li>"

    market_html = ""
    if market.get("volume_top"):
        market_html += f"<p>📊 거래량 상위: {' | '.join(market['volume_top'][:3])}</p>"
    if market.get("rise_top"):
        market_html += f"<p>🔴 상승 상위: {' | '.join(market['rise_top'][:3])}</p>"

    return f"""<html>
<body style="font-family: '맑은 고딕', Arial; background: #1a1a1a; color: #e8e8e8; padding: 20px;">
<h1 style="color: #FFD700; border-bottom: 2px solid #FFD700; padding-bottom: 8px;">
  📋 오늘의 투자 정보지 — {today_str}
</h1>
<p style="color: #aaa; font-size: 12px;">※ AI API 키 설정 후 더 정밀한 분석이 제공됩니다 (설정 → API 키 설정)</p>

<h2 style="color: #FF6B35;">📰 오늘의 주요 뉴스</h2>
<ul style="line-height: 1.8;">{news_html}</ul>

<h2 style="color: #FF6B35;">📈 시장 동향</h2>
{market_html if market_html else '<p>시장 데이터를 불러오는 중입니다...</p>'}

<hr style="border-color: #444;">
<p style="color: #888; font-size: 11px; text-align: center;">
  이 정보지는 AI가 공개 데이터를 분석하여 생성한 참고 자료입니다.<br>
  투자 결정은 본인 판단으로 하시기 바랍니다.
</p>
</body>
</html>"""
