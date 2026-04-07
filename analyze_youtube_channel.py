#!/usr/bin/env python3
"""
YouTube 채널 영상 자막 수집 및 투자 원칙 분석 스크립트
"""

import os
import sys
import time
import json
from urllib.request import urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError

# ── 패키지 자동 설치 ──────────────────────────────────────────────
def install(package):
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", package])

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    print("youtube-transcript-api 설치 중...")
    install("youtube-transcript-api")
    from youtube_transcript_api import YouTubeTranscriptApi

try:
    import anthropic
except ImportError:
    print("anthropic 설치 중...")
    install("anthropic")
    import anthropic

# ── API 키 입력 ───────────────────────────────────────────────────
print("=" * 60)
print("  YouTube 채널 투자 원칙 분석기")
print("=" * 60)
print()

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY") or input("YouTube Data API 키를 입력하세요: ").strip()
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY") or input("Anthropic API 키를 입력하세요: ").strip()

CHANNEL_HANDLE = "@TV-lb7cv"

# ── YouTube API 헬퍼 ──────────────────────────────────────────────
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
    """@핸들로 채널 ID 조회"""
    print(f"\n채널 검색 중: {handle}")
    data = youtube_get("search", {
        "part": "snippet",
        "q": handle,
        "type": "channel",
        "maxResults": 5
    })
    if not data or not data.get("items"):
        # forHandle API 시도
        data = youtube_get("channels", {
            "part": "id,snippet",
            "forHandle": handle.lstrip("@")
        })
        if data and data.get("items"):
            ch = data["items"][0]
            print(f"  채널명: {ch['snippet']['title']}")
            return ch["id"]
        return None

    # 검색 결과에서 핸들 매칭
    for item in data["items"]:
        ch_id = item["snippet"]["channelId"]
        ch_data = youtube_get("channels", {"part": "id,snippet,contentDetails", "id": ch_id})
        if ch_data and ch_data.get("items"):
            ch = ch_data["items"][0]
            print(f"  채널명: {ch['snippet']['title']}")
            return ch["id"]
    return None

def get_all_video_ids(channel_id):
    """채널의 모든 영상 ID 수집"""
    # uploads 재생목록 ID 조회
    data = youtube_get("channels", {
        "part": "contentDetails,snippet",
        "id": channel_id
    })
    if not data or not data.get("items"):
        return []

    uploads_id = data["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    channel_title = data["items"][0]["snippet"]["title"]
    print(f"  업로드 재생목록 ID: {uploads_id}")

    # 전체 영상 목록 수집 (페이지네이션)
    videos = []
    next_page = None
    while True:
        params = {
            "part": "snippet",
            "playlistId": uploads_id,
            "maxResults": 50
        }
        if next_page:
            params["pageToken"] = next_page

        data = youtube_get("playlistItems", params)
        if not data:
            break

        for item in data.get("items", []):
            vid_id = item["snippet"]["resourceId"]["videoId"]
            title = item["snippet"]["title"]
            videos.append({"id": vid_id, "title": title})

        next_page = data.get("nextPageToken")
        if not next_page:
            break

    return videos

def get_transcript(video_id, title):
    """자막 가져오기 - 가능한 모든 방법 시도"""
    api = YouTubeTranscriptApi()

    try:
        transcript_list = api.list(video_id)
        transcripts = list(transcript_list)

        if not transcripts:
            print(f"(자막 목록 자체가 비어있음)", end=" ")
            return None

        available = [f"{t.language_code}({'자동' if t.is_generated else '수동'})" for t in transcripts]
        print(f"(사용 가능: {', '.join(available)})", end=" ")

        # 1순위: 수동 한국어
        for t in transcripts:
            if t.language_code in ("ko", "ko-KR") and not t.is_generated:
                text = " ".join(chunk.text for chunk in t.fetch())
                return text

        # 2순위: 자동 생성 한국어
        for t in transcripts:
            if t.language_code in ("ko", "ko-KR"):
                text = " ".join(chunk.text for chunk in t.fetch())
                return text

        # 3순위: 번역 가능한 자막을 한국어로 번역
        for t in transcripts:
            if t.is_translatable:
                try:
                    text = " ".join(chunk.text for chunk in t.translate("ko").fetch())
                    return text
                except Exception:
                    pass

        # 4순위: 아무 자막이나 가져오기
        t = transcripts[0]
        text = " ".join(chunk.text for chunk in t.fetch())
        return text

    except Exception as e:
        print(f"({type(e).__name__}: {str(e)[:60]})", end=" ")
        return None

# ── Claude 분석 ───────────────────────────────────────────────────
def analyze_with_claude(transcripts_data):
    """모든 자막을 Claude로 분석"""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # 자막 텍스트 합치기 (너무 길면 나눠서 처리)
    combined = ""
    for item in transcripts_data:
        combined += f"\n\n[영상: {item['title']}]\n{item['transcript']}"

    # 너무 길면 앞부분만 (Claude 컨텍스트 제한 고려)
    max_chars = 150000
    if len(combined) > max_chars:
        print(f"\n  (자막이 너무 길어 앞 {max_chars:,}자만 분석합니다)")
        combined = combined[:max_chars]

    print("\nClaude로 분석 중... (잠시 기다려주세요)")

    prompt = f"""다음은 유튜브 채널 영상들의 자막 내용입니다.

{combined}

---

위 내용을 바탕으로, 이 유튜버의 **핵심 투자 원칙**을 카테고리별로 정리해주세요.

규칙:
- 반드시 영상에서 실제로 언급된 내용만 추출할 것
- 추측이나 일반적인 투자 상식은 포함하지 말 것
- 각 원칙마다 영상에서 언급된 구체적인 표현이나 예시를 함께 적을 것
- 카테고리는 내용에 맞게 자연스럽게 분류할 것

형식:
## 카테고리명
- **원칙**: 설명 (영상 내 언급된 표현 또는 예시)
"""

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text

# ── 메인 실행 ─────────────────────────────────────────────────────
def main():
    # 1. 채널 ID 조회
    channel_id = get_channel_id(CHANNEL_HANDLE)
    if not channel_id:
        print("채널을 찾을 수 없습니다. API 키와 채널 핸들을 확인하세요.")
        sys.exit(1)

    # 2. 전체 영상 목록
    print("\n영상 목록 수집 중...")
    videos = get_all_video_ids(channel_id)
    print(f"  총 {len(videos)}개 영상 발견")

    if not videos:
        print("영상을 찾을 수 없습니다.")
        sys.exit(1)

    # 3. 자막 수집
    print("\n자막 수집 중...")
    transcripts_data = []
    failed = []

    for i, video in enumerate(videos, 1):
        print(f"  [{i}/{len(videos)}] {video['title'][:50]}", end=" ")
        transcript = get_transcript(video["id"], video["title"])
        if transcript:
            transcripts_data.append({
                "title": video["title"],
                "id": video["id"],
                "transcript": transcript
            })
            print(f"✓ ({len(transcript):,}자)")
        else:
            failed.append(video["title"])
            print("✗ (자막 없음)")
        time.sleep(0.5)  # API 요청 간격

    print(f"\n  자막 수집 완료: {len(transcripts_data)}개 성공, {len(failed)}개 실패")

    if not transcripts_data:
        print("분석할 자막이 없습니다.")
        sys.exit(1)

    # 4. Claude 분석
    result = analyze_with_claude(transcripts_data)

    # 5. 결과 출력 및 저장
    print("\n" + "=" * 60)
    print("  분석 결과")
    print("=" * 60)
    print(result)

    output_file = "investment_principles.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"# {CHANNEL_HANDLE} 핵심 투자 원칙 분석\n\n")
        f.write(f"- 분석 영상 수: {len(transcripts_data)}개\n")
        f.write(f"- 자막 없는 영상: {len(failed)}개\n\n")
        f.write("---\n\n")
        f.write(result)

    print(f"\n결과가 '{output_file}'에 저장되었습니다.")

if __name__ == "__main__":
    main()
