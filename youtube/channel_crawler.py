"""
YouTube 채널 크롤러
yt-dlp를 사용하여 채널의 모든 영상 정보를 수집하고 DB에 저장합니다.
"""

import subprocess
import json
import sqlite3
import logging
from pathlib import Path
from typing import Callable, Optional
from datetime import datetime

from config import DB_PATH, MAX_VIDEOS

logger = logging.getLogger(__name__)


def init_db():
    """데이터베이스 테이블 초기화"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            video_id TEXT PRIMARY KEY,
            title TEXT,
            channel_name TEXT,
            upload_date TEXT,
            duration INTEGER,
            view_count INTEGER,
            url TEXT,
            transcript_fetched INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS transcripts (
            video_id TEXT PRIMARY KEY,
            text TEXT,
            language TEXT,
            fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (video_id) REFERENCES videos(video_id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS principles (
            id TEXT PRIMARY KEY,
            category TEXT,
            title TEXT,
            description TEXT,
            conditions TEXT,
            indicators TEXT,
            keywords TEXT,
            channel_url TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS analysis_meta (
            channel_url TEXT PRIMARY KEY,
            channel_name TEXT,
            total_videos INTEGER,
            analyzed_videos INTEGER,
            summary TEXT,
            last_analyzed TEXT
        )
    """)
    conn.commit()
    conn.close()


def get_channel_videos(
    channel_url: str,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> list[dict]:
    """
    yt-dlp로 채널의 모든 영상 메타데이터를 수집합니다.

    Args:
        channel_url: 유튜브 채널 URL
        progress_callback: (current, total, message) 형태의 진행 콜백

    Returns:
        영상 정보 딕셔너리 리스트
    """
    logger.info(f"채널 영상 목록 수집 시작: {channel_url}")

    # yt-dlp로 채널 전체 영상 메타데이터 가져오기 (다운로드 없이)
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-single-json",
        "--no-warnings",
        "--ignore-errors",
    ]

    if MAX_VIDEOS > 0:
        cmd += ["--playlist-end", str(MAX_VIDEOS)]

    cmd.append(channel_url)

    try:
        if progress_callback:
            progress_callback(0, 0, "채널 영상 목록 수집 중...")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )

        if result.returncode != 0 and not result.stdout:
            logger.error(f"yt-dlp 오류: {result.stderr}")
            raise RuntimeError(f"채널 정보를 가져올 수 없습니다: {result.stderr[:200]}")

        data = json.loads(result.stdout)
        entries = data.get("entries", [])

        # None 항목 제거 (비공개/삭제된 영상)
        entries = [e for e in entries if e is not None]

        logger.info(f"총 {len(entries)}개 영상 발견")

        videos = []
        for i, entry in enumerate(entries):
            if progress_callback:
                progress_callback(i + 1, len(entries), f"영상 정보 처리 중 ({i+1}/{len(entries)})")

            video = {
                "video_id": entry.get("id", ""),
                "title": entry.get("title", ""),
                "channel_name": entry.get("channel", data.get("channel", "")),
                "upload_date": entry.get("upload_date", ""),
                "duration": entry.get("duration", 0),
                "view_count": entry.get("view_count", 0),
                "url": f"https://www.youtube.com/watch?v={entry.get('id', '')}",
            }

            if video["video_id"]:
                videos.append(video)

        return videos

    except subprocess.TimeoutExpired:
        raise RuntimeError("채널 정보 수집 시간 초과 (2분). 채널 URL을 확인하세요.")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"응답 파싱 오류: {e}")


def save_videos_to_db(videos: list[dict], channel_url: str = ""):
    """영상 목록을 DB에 저장 (중복 무시)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    saved = 0
    for v in videos:
        try:
            c.execute(
                """INSERT OR IGNORE INTO videos
                   (video_id, title, channel_name, upload_date, duration, view_count, url)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    v["video_id"],
                    v["title"],
                    v["channel_name"],
                    v["upload_date"],
                    v["duration"],
                    v["view_count"],
                    v["url"],
                ),
            )
            if c.rowcount > 0:
                saved += 1
        except Exception as e:
            logger.warning(f"영상 저장 실패 {v.get('video_id')}: {e}")
    conn.commit()
    conn.close()
    logger.info(f"{saved}개 영상 DB 저장 완료 (중복 제외)")
    return saved


def get_all_videos_from_db(channel_name: str = "") -> list[dict]:
    """DB에서 영상 목록 조회"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if channel_name:
        c.execute(
            "SELECT video_id, title, url, transcript_fetched FROM videos WHERE channel_name=? ORDER BY upload_date DESC",
            (channel_name,),
        )
    else:
        c.execute(
            "SELECT video_id, title, url, transcript_fetched FROM videos ORDER BY upload_date DESC"
        )
    rows = c.fetchall()
    conn.close()
    return [
        {"video_id": r[0], "title": r[1], "url": r[2], "transcript_fetched": r[3]}
        for r in rows
    ]


def crawl_channel(
    channel_url: str,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> list[dict]:
    """
    채널 크롤링 메인 함수.
    영상 목록을 수집하고 DB에 저장한 후 반환합니다.
    """
    init_db()
    videos = get_channel_videos(channel_url, progress_callback)
    save_videos_to_db(videos, channel_url)
    return videos
