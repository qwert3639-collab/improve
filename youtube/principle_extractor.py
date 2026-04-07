"""
투자 원칙 추출기
Claude API를 사용하여 유튜브 자막에서 투자 원칙을 분석하고 추출합니다.
배치 처리로 토큰 한도를 고려합니다.
"""

import json
import sqlite3
import logging
from typing import Callable, Optional
from datetime import datetime

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    DB_PATH,
    PRINCIPLE_EXTRACTION_SYSTEM_PROMPT,
    PRINCIPLE_EXTRACTION_USER_PROMPT,
    STOCK_RECOMMENDATION_PROMPT,
)

logger = logging.getLogger(__name__)

# 한 번에 Claude에 보낼 최대 자막 문자 수
BATCH_CHAR_LIMIT = 60_000


def _call_claude(system_prompt: str, user_prompt: str) -> str:
    """Claude API 호출 헬퍼"""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return message.content[0].text


def _split_into_batches(
    transcripts: dict[str, str], batch_size: int = BATCH_CHAR_LIMIT
) -> list[str]:
    """자막 딕셔너리를 토큰 크기에 맞는 배치로 분할"""
    batches = []
    current_batch = []
    current_size = 0

    for video_id, text in transcripts.items():
        chunk = f"\n[영상 {video_id}]\n{text}\n"
        if current_size + len(chunk) > batch_size and current_batch:
            batches.append("\n".join(current_batch))
            current_batch = [chunk]
            current_size = len(chunk)
        else:
            current_batch.append(chunk)
            current_size += len(chunk)

    if current_batch:
        batches.append("\n".join(current_batch))

    return batches


def extract_principles_from_transcripts(
    transcripts: dict[str, str],
    channel_url: str = "",
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> list[dict]:
    """
    자막에서 투자 원칙을 추출합니다.
    여러 배치로 분할하여 처리하고 결과를 통합합니다.

    Args:
        transcripts: {video_id: text} 딕셔너리
        channel_url: 채널 URL (메타 저장용)
        progress_callback: 진행 콜백

    Returns:
        원칙 딕셔너리 리스트
    """
    if not transcripts:
        raise ValueError("분석할 자막이 없습니다.")

    batches = _split_into_batches(transcripts)
    total_batches = len(batches)
    logger.info(f"총 {total_batches}개 배치로 분할하여 분석합니다.")

    all_principles = []
    all_summaries = []

    for i, batch_text in enumerate(batches):
        if progress_callback:
            progress_callback(
                i + 1,
                total_batches,
                f"AI 분석 중 ({i+1}/{total_batches}배치)...",
            )

        logger.info(f"배치 {i+1}/{total_batches} 분석 중 ({len(batch_text):,}자)")

        prompt = PRINCIPLE_EXTRACTION_USER_PROMPT.format(transcripts=batch_text)

        try:
            response_text = _call_claude(PRINCIPLE_EXTRACTION_SYSTEM_PROMPT, prompt)

            # JSON 파싱 (마크다운 코드블록 제거)
            clean = response_text.strip()
            if clean.startswith("```"):
                lines = clean.split("\n")
                clean = "\n".join(lines[1:-1])

            data = json.loads(clean)
            batch_principles = data.get("principles", [])
            batch_summary = data.get("summary", "")

            all_principles.extend(batch_principles)
            if batch_summary:
                all_summaries.append(batch_summary)

            logger.info(f"배치 {i+1}: {len(batch_principles)}개 원칙 추출")

        except json.JSONDecodeError as e:
            logger.error(f"배치 {i+1} JSON 파싱 실패: {e}")
            logger.debug(f"응답: {response_text[:500]}")
            continue
        except Exception as e:
            logger.error(f"배치 {i+1} 분석 오류: {e}")
            continue

    # 배치가 여러 개인 경우 최종 통합 분석
    if total_batches > 1 and all_principles:
        if progress_callback:
            progress_callback(total_batches, total_batches, "원칙 통합 분석 중...")

        all_principles = _merge_and_deduplicate(all_principles)

    # DB에 저장
    if all_principles:
        save_principles_to_db(all_principles, channel_url, "\n".join(all_summaries))

    return all_principles


def _merge_and_deduplicate(principles: list[dict]) -> list[dict]:
    """여러 배치에서 추출된 원칙을 통합하고 중복을 제거합니다."""
    # 제목 기반 중복 제거
    seen_titles = {}
    merged = []

    for p in principles:
        title = p.get("title", "").strip()
        if title not in seen_titles:
            seen_titles[title] = len(merged)
            # ID 재부여
            p["id"] = f"P{len(merged)+1:03d}"
            merged.append(p)

    return merged


def save_principles_to_db(
    principles: list[dict], channel_url: str = "", summary: str = ""
):
    """추출된 원칙을 DB에 저장"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 기존 원칙 삭제 (재분석 시 갱신)
    if channel_url:
        c.execute("DELETE FROM principles WHERE channel_url=?", (channel_url,))

    for p in principles:
        c.execute(
            """INSERT OR REPLACE INTO principles
               (id, category, title, description, conditions, indicators, keywords, channel_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                p.get("id", ""),
                p.get("category", ""),
                p.get("title", ""),
                p.get("description", ""),
                json.dumps(p.get("conditions", []), ensure_ascii=False),
                json.dumps(p.get("indicators", []), ensure_ascii=False),
                json.dumps(p.get("keywords", []), ensure_ascii=False),
                channel_url,
            ),
        )

    # 분석 메타 정보 저장
    c.execute(
        """INSERT OR REPLACE INTO analysis_meta
           (channel_url, analyzed_videos, summary, last_analyzed)
           VALUES (?, ?, ?, ?)""",
        (
            channel_url,
            0,
            summary,
            datetime.now().isoformat(),
        ),
    )

    conn.commit()
    conn.close()
    logger.info(f"{len(principles)}개 원칙 DB 저장 완료")


def load_principles_from_db(channel_url: str = "") -> list[dict]:
    """DB에서 원칙 로드"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    if channel_url:
        c.execute(
            "SELECT id, category, title, description, conditions, indicators, keywords FROM principles WHERE channel_url=?",
            (channel_url,),
        )
    else:
        c.execute(
            "SELECT id, category, title, description, conditions, indicators, keywords FROM principles"
        )

    rows = c.fetchall()
    conn.close()

    principles = []
    for r in rows:
        principles.append(
            {
                "id": r[0],
                "category": r[1],
                "title": r[2],
                "description": r[3],
                "conditions": json.loads(r[4]) if r[4] else [],
                "indicators": json.loads(r[5]) if r[5] else [],
                "keywords": json.loads(r[6]) if r[6] else [],
            }
        )
    return principles


def analyze_stocks_with_principles(
    principles: list[dict],
    stock_data_list: list[dict],
) -> list[dict]:
    """
    투자 원칙을 기반으로 종목 데이터를 AI가 분석하여 추천을 생성합니다.

    Args:
        principles: 투자 원칙 리스트
        stock_data_list: [{code, name, price, change_rate, volume, ...}] 리스트

    Returns:
        추천 결과 리스트 (점수 높은 순)
    """
    if not principles or not stock_data_list:
        return []

    principles_text = json.dumps(principles, ensure_ascii=False, indent=2)
    stock_text = json.dumps(stock_data_list[:50], ensure_ascii=False, indent=2)  # 최대 50개

    prompt = STOCK_RECOMMENDATION_PROMPT.format(
        principles=principles_text,
        stock_data=stock_text,
    )

    system = "당신은 주식 투자 분석가입니다. 투자 원칙을 기반으로 종목을 분석하고 JSON으로 출력합니다."

    try:
        response_text = _call_claude(system, prompt)

        clean = response_text.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1])

        data = json.loads(clean)
        recommendations = data.get("recommendations", [])

        # 점수 기준 정렬
        recommendations.sort(key=lambda x: x.get("score", 0), reverse=True)
        return recommendations

    except Exception as e:
        logger.error(f"종목 분석 오류: {e}")
        return []
