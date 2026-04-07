"""
YouTube 자막 추출기
youtube-transcript-api로 영상의 한국어 자막을 추출하고 캐싱합니다.
"""

import sqlite3
import json
import logging
import time
from pathlib import Path
from typing import Callable, Optional

from config import DB_PATH, CACHE_DIR, TRANSCRIPT_LANGUAGES

logger = logging.getLogger(__name__)


def _get_transcript_text(video_id: str) -> tuple[str, str]:
    """
    영상 ID로 자막 텍스트를 가져옵니다.
    한국어 자막 → 자동 생성 자막 순으로 시도합니다.

    Returns:
        (자막 텍스트, 언어코드) 튜플
    """
    from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound

    # 한국어 자막 우선 시도
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # 수동 자막 (업로더가 직접 올린 것) 먼저 시도
        for lang in TRANSCRIPT_LANGUAGES:
            try:
                t = transcript_list.find_manually_created_transcript([lang])
                data = t.fetch()
                text = " ".join([item["text"] for item in data])
                return text, lang
            except Exception:
                pass

        # 자동 생성 자막 시도
        for lang in TRANSCRIPT_LANGUAGES:
            try:
                t = transcript_list.find_generated_transcript([lang])
                data = t.fetch()
                text = " ".join([item["text"] for item in data])
                return text, f"{lang}-auto"
            except Exception:
                pass

        # 영어 자막을 한국어로 번역 시도
        try:
            t = transcript_list.find_transcript(["en"])
            translated = t.translate("ko")
            data = translated.fetch()
            text = " ".join([item["text"] for item in data])
            return text, "ko-translated"
        except Exception:
            pass

        raise NoTranscriptFound(video_id, TRANSCRIPT_LANGUAGES, None)

    except Exception as e:
        raise RuntimeError(f"자막 없음: {e}")


def fetch_transcript(video_id: str, use_cache: bool = True) -> Optional[str]:
    """
    단일 영상의 자막을 가져옵니다. DB 캐시를 먼저 확인합니다.

    Args:
        video_id: 유튜브 영상 ID
        use_cache: True면 DB 캐시 사용

    Returns:
        자막 텍스트 또는 None (자막 없을 경우)
    """
    if use_cache:
        # DB 캐시 확인
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT text FROM transcripts WHERE video_id=?", (video_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return row[0]

    try:
        text, lang = _get_transcript_text(video_id)

        # DB에 저장
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO transcripts (video_id, text, language) VALUES (?, ?, ?)",
            (video_id, text, lang),
        )
        c.execute(
            "UPDATE videos SET transcript_fetched=1 WHERE video_id=?",
            (video_id,),
        )
        conn.commit()
        conn.close()

        logger.debug(f"자막 추출 완료: {video_id} ({lang})")
        return text

    except Exception as e:
        logger.warning(f"자막 추출 실패 {video_id}: {e}")
        # 실패도 기록 (재시도 방지를 위해 빈 텍스트 저장)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "UPDATE videos SET transcript_fetched=-1 WHERE video_id=?",
            (video_id,),
        )
        conn.commit()
        conn.close()
        return None


def fetch_all_transcripts(
    video_ids: list[str],
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    delay: float = 0.5,
) -> dict[str, str]:
    """
    여러 영상의 자막을 일괄 추출합니다.

    Args:
        video_ids: 영상 ID 리스트
        progress_callback: (current, total, message) 콜백
        delay: 요청 간 딜레이 (초) - YouTube 차단 방지

    Returns:
        {video_id: transcript_text} 딕셔너리
    """
    results = {}
    total = len(video_ids)

    for i, video_id in enumerate(video_ids):
        if progress_callback:
            progress_callback(i + 1, total, f"자막 추출 중 ({i+1}/{total}): {video_id}")

        text = fetch_transcript(video_id)
        if text:
            results[video_id] = text

        # 과도한 요청 방지
        if i < total - 1:
            time.sleep(delay)

    logger.info(f"자막 추출 완료: {len(results)}/{total}개 성공")
    return results


def get_all_transcripts_from_db() -> dict[str, str]:
    """DB에서 모든 자막을 가져옵니다."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT video_id, text FROM transcripts WHERE text != ''")
    rows = c.fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}


def get_unfetched_video_ids() -> list[str]:
    """아직 자막을 가져오지 않은 영상 ID 목록 반환"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # transcript_fetched=0: 미시도, -1: 실패(스킵)
    c.execute("SELECT video_id FROM videos WHERE transcript_fetched=0")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]


def build_combined_transcript(
    transcripts: dict[str, str],
    max_chars: int = 80000,
) -> str:
    """
    여러 영상의 자막을 하나의 텍스트로 합칩니다.
    Claude API 토큰 한도를 고려하여 max_chars로 제한합니다.
    """
    combined = []
    total_chars = 0

    for video_id, text in transcripts.items():
        chunk = f"\n[영상 {video_id}]\n{text}\n"
        if total_chars + len(chunk) > max_chars:
            # 남은 공간만큼 잘라서 추가
            remaining = max_chars - total_chars
            if remaining > 200:
                combined.append(chunk[:remaining] + "...(생략)")
            break
        combined.append(chunk)
        total_chars += len(chunk)

    return "\n".join(combined)
