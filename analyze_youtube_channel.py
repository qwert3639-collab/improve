#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube channel transcript collector and investment principles analyzer
"""

import os
import sys
import time
import json
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from urllib.error import HTTPError

# Auto-install packages
def install(package):
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", package])

try:
    import google.generativeai as genai
except ImportError:
    print("google-generativeai 설치 중...")
    install("google-generativeai")
    import google.generativeai as genai

# ── API 키 입력 ──────────────────────────────────────────────────────
print("=" * 60)
print("  YouTube 채널 투자 원칙 분석기")
print("=" * 60)
print()

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY") or input("YouTube Data API 키: ").strip()
GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY")  or input("Gemini API 키: ").strip()

CHANNEL_HANDLE = "@TV-lb7cv"

genai.configure(api_key=GEMINI_API_KEY)

# ── YouTube Data API ─────────────────────────────────────────────────
def youtube_get(endpoint, params):
    params["key"] = YOUTUBE_API_KEY
    url = f"https://www.googleapis.com/youtube/v3/{endpoint}?{urlencode(params)}"
    try:
        with urlopen(url) as r:
            return json.loads(r.read())
    except HTTPError as e:
        print(f"  YouTube API 오류: {e.code} {e.reason}")
        return None

def get_channel_id(handle):
    print(f"\n채널 검색 중: {handle}")
    data = youtube_get("channels", {
        "part": "id,snippet",
        "forHandle": handle.lstrip("@")
    })
    if data and data.get("items"):
        ch = data["items"][0]
        print(f"  채널명: {ch['snippet']['title']}")
        return ch["id"]

    data = youtube_get("search", {"part": "snippet", "q": handle, "type": "channel", "maxResults": 5})
    if data and data.get("items"):
        ch_id = data["items"][0]["snippet"]["channelId"]
        ch_data = youtube_get("channels", {"part": "id,snippet,contentDetails", "id": ch_id})
        if ch_data and ch_data.get("items"):
            ch = ch_data["items"][0]
            print(f"  채널명: {ch['snippet']['title']}")
            return ch["id"]
    return None

def get_all_video_ids(channel_id):
    data = youtube_get("channels", {"part": "contentDetails", "id": channel_id})
    if not data or not data.get("items"):
        return []

    uploads_id = data["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    print(f"  업로드 재생목록 ID: {uploads_id}")

    videos = []
    next_page = None
    while True:
        params = {"part": "snippet", "playlistId": uploads_id, "maxResults": 50}
        if next_page:
            params["pageToken"] = next_page
        data = youtube_get("playlistItems", params)
        if not data:
            break
        for item in data.get("items", []):
            vid_id = item["snippet"]["resourceId"]["videoId"]
            title  = item["snippet"]["title"]
            videos.append({"id": vid_id, "title": title})
        next_page = data.get("nextPageToken")
        if not next_page:
            break
    return videos

# ── Gemini로 자막 추출 ───────────────────────────────────────────────
def get_transcript_gemini(video_id, title):
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(
            [
                url,
                "이 유튜브 영상의 전체 대화 내용을 한국어로 최대한 자세히 추출해줘. "
                "요약하지 말고 실제 말한 내용을 그대로 적어줘. "
                "영상에서 언급된 투자 관련 내용, 종목명, 수치, 전략을 빠짐없이 포함해줘."
            ]
        )
        text = response.text.strip()
        return text if text else None
    except Exception as e:
        err = str(e)[:80]
        print(f"(Gemini 오류: {err})", end=" ", flush=True)
        return None

# ── Gemini로 분석 ────────────────────────────────────────────────────
def analyze_with_gemini(transcripts_data):
    combined = ""
    for item in transcripts_data:
        combined += f"\n\n[영상: {item['title']}]\n{item['transcript']}"

    max_chars = 180000
    if len(combined) > max_chars:
        print(f"\n  (자막이 너무 길어 앞 {max_chars:,}자만 분석합니다)")
        combined = combined[:max_chars]

    print("\nGemini로 분석 중... (잠시 기다려주세요)")

    prompt = f"""다음은 유튜브 채널 '창원개미TV' 영상들의 내용입니다.

{combined}

---

위 내용을 바탕으로, 이 유튜버의 핵심 투자 원칙을 카테고리별로 정리해주세요.

규칙:
- 반드시 영상에서 실제로 언급된 내용만 추출할 것
- 추측이나 일반적인 투자 상식은 포함하지 말 것
- 각 원칙마다 영상에서 언급된 구체적인 표현이나 예시를 함께 적을 것
- 카테고리는 내용에 맞게 자연스럽게 분류할 것

형식:
## 카테고리명
- **원칙**: 설명 (영상 내 언급된 표현 또는 예시)
"""

    model = genai.GenerativeModel("gemini-1.5-pro")
    response = model.generate_content(prompt)
    return response.text

# ── 메인 ─────────────────────────────────────────────────────────────
def main():
    channel_id = get_channel_id(CHANNEL_HANDLE)
    if not channel_id:
        print("채널을 찾을 수 없습니다.")
        sys.exit(1)

    print("\n영상 목록 수집 중...")
    videos = get_all_video_ids(channel_id)
    print(f"  총 {len(videos)}개 영상 발견")

    if not videos:
        print("영상을 찾을 수 없습니다.")
        sys.exit(1)

    print("\n자막 수집 중... (Gemini API 사용)")
    transcripts_data = []
    failed = []

    for i, video in enumerate(videos, 1):
        print(f"  [{i}/{len(videos)}] {video['title'][:50]}", end=" ", flush=True)
        transcript = get_transcript_gemini(video["id"], video["title"])
        if transcript:
            transcripts_data.append({
                "title": video["title"],
                "id": video["id"],
                "transcript": transcript
            })
            print(f"✓ ({len(transcript):,}자)")
        else:
            failed.append(video["title"])
            print("✗ (실패)")
        time.sleep(1)  # Gemini API rate limit

    print(f"\n  수집 완료: {len(transcripts_data)}개 성공, {len(failed)}개 실패")

    if not transcripts_data:
        print("분석할 내용이 없습니다.")
        sys.exit(1)

    result = analyze_with_gemini(transcripts_data)

    print("\n" + "=" * 60)
    print("  분석 결과")
    print("=" * 60)
    print(result)

    output_file = "investment_principles.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"# 창원개미TV 핵심 투자 원칙 분석\n\n")
        f.write(f"- 분석 영상 수: {len(transcripts_data)}개\n")
        f.write(f"- 실패한 영상: {len(failed)}개\n\n")
        f.write("---\n\n")
        f.write(result)

    print(f"\n결과가 '{output_file}'에 저장되었습니다.")

if __name__ == "__main__":
    main()
