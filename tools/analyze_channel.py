"""
유튜브 채널 전체 분석 독립 실행 스크립트
Windows PC에서 직접 실행하세요:
  python tools/analyze_channel.py

채널의 모든 영상 자막을 수집하고
Claude/OpenAI/Gemini로 투자 원칙을 추출합니다.
결과는 data/principles_raw.json 에 저장됩니다.
"""

import sys
import os
import json
import time
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime

# 프로젝트 루트를 path에 추가
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ── 설정 ──────────────────────────────────────────────────────────────────────
CHANNEL_URL = "https://www.youtube.com/@TV-lb7cv"
OUTPUT_DIR = ROOT / "data"
TRANSCRIPT_CACHE = OUTPUT_DIR / "transcripts_cache.json"
PRINCIPLES_OUTPUT = OUTPUT_DIR / "principles_raw.json"
MAX_VIDEOS = 0       # 0 = 전체
DELAY_BETWEEN = 0.5  # 자막 요청 간격(초)

# ── .env 로드 ──────────────────────────────────────────────────────────────────
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

AI_PROVIDER = os.environ.get("AI_PROVIDER", "claude")
AI_API_KEY  = os.environ.get("AI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
AI_MODEL    = os.environ.get("AI_MODEL", "claude-haiku-4-5-20251001")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: 채널 영상 목록 수집 (yt-dlp CLI)
# ══════════════════════════════════════════════════════════════════════════════

def get_video_ids(channel_url: str) -> list[dict]:
    print(f"\n[1/3] 채널 영상 목록 수집 중: {channel_url}")

    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--print", "%(id)s|%(title)s|%(duration)s",
        "--no-warnings",
        "--ignore-errors",
    ]
    if MAX_VIDEOS > 0:
        cmd += ["--playlist-end", str(MAX_VIDEOS)]
    cmd.append(channel_url)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=120)
        lines = [l.strip() for l in result.stdout.splitlines() if "|" in l]

        videos = []
        for line in lines:
            parts = line.split("|")
            if len(parts) >= 2 and parts[0]:
                videos.append({
                    "id": parts[0],
                    "title": parts[1] if len(parts) > 1 else "",
                    "duration": int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0,
                })

        print(f"  → {len(videos)}개 영상 발견")
        return videos

    except subprocess.TimeoutExpired:
        print("  [오류] 시간 초과. 네트워크 확인 후 재시도하세요.")
        sys.exit(1)
    except FileNotFoundError:
        print("  [오류] yt-dlp가 설치되지 않았습니다.")
        print("  실행: pip install yt-dlp")
        sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: 자막 수집 (youtube-transcript-api)
# ══════════════════════════════════════════════════════════════════════════════

def get_transcripts(videos: list[dict]) -> dict[str, str]:
    print(f"\n[2/3] 자막 수집 중 ({len(videos)}개 영상)...")

    # 캐시 로드
    cache = {}
    if TRANSCRIPT_CACHE.exists():
        cache = json.loads(TRANSCRIPT_CACHE.read_text(encoding="utf-8"))
        print(f"  캐시 로드: {len(cache)}개 기존 자막")

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        print("  [오류] youtube-transcript-api 미설치")
        print("  실행: pip install youtube-transcript-api")
        sys.exit(1)

    api = YouTubeTranscriptApi()
    success = 0
    fail = 0

    for i, video in enumerate(videos):
        vid = video["id"]

        if vid in cache:
            success += 1
            continue

        try:
            snippets = api.fetch(vid, languages=["ko", "ko-KR"])
            text = " ".join(s.text for s in snippets if hasattr(s, 'text'))
            if not text:
                # 다른 방식 시도
                text = " ".join(str(s) for s in snippets)
            cache[vid] = {
                "title": video["title"],
                "text": text,
                "lang": "ko",
            }
            success += 1

            # 진행 표시
            pct = int((i + 1) / len(videos) * 100)
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            print(f"\r  [{bar}] {pct}% ({i+1}/{len(videos)}) 성공:{success} 실패:{fail}", end="", flush=True)

            # 중간 저장 (50개마다)
            if (i + 1) % 50 == 0:
                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                TRANSCRIPT_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

        except Exception as e:
            fail += 1
            # 한국어 자막 없으면 영어 시도
            try:
                snippets = api.fetch(vid, languages=["en"])
                text = " ".join(s.text for s in snippets if hasattr(s, 'text'))
                cache[vid] = {"title": video["title"], "text": text, "lang": "en"}
                success += 1
            except Exception:
                cache[vid] = {"title": video["title"], "text": "", "lang": "none"}

        time.sleep(DELAY_BETWEEN)

    print()  # 줄바꿈

    # 최종 저장
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TRANSCRIPT_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    valid = {vid: data for vid, data in cache.items() if data.get("text")}
    print(f"  → 자막 수집 완료: {len(valid)}개 성공 / {len(videos) - len(valid)}개 실패")
    print(f"  캐시 저장: {TRANSCRIPT_CACHE}")
    return {vid: data["text"] for vid, data in valid.items()}


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: AI 분석 - 투자 원칙 추출
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """당신은 주식 투자 전문가입니다.
유튜브 주식 투자 채널의 영상 자막을 분석하여 이 유튜버의 핵심 투자 원칙을 추출합니다.

중요: 반드시 영상 내용에서 실제로 언급된 내용만 추출하세요.
일반적인 투자 원칙을 임의로 추가하지 마세요.

JSON 형식으로만 응답하세요:
{
  "principles": [
    {
      "id": "P001",
      "category": "종목선택 | 매수시점 | 매도시점 | 리스크관리 | 시장분석",
      "title": "원칙 제목 (15자 이내)",
      "description": "영상에서 언급된 구체적 내용",
      "conditions": ["구체적 조건1", "조건2"],
      "indicators": ["사용 지표/기준"],
      "keywords": ["핵심 키워드"],
      "evidence": "이 원칙이 언급된 영상 내용 발췌 (50자)"
    }
  ],
  "channel_style": "이 채널의 전체 투자 스타일 요약 (100자)"
}"""


def _call_ai(prompt: str) -> str:
    """AI API 호출"""
    if AI_PROVIDER == "claude":
        import anthropic
        client = anthropic.Anthropic(api_key=AI_API_KEY)
        msg = client.messages.create(
            model=AI_MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text

    elif AI_PROVIDER == "openai":
        import openai
        client = openai.OpenAI(api_key=AI_API_KEY)
        resp = client.chat.completions.create(
            model=AI_MODEL or "gpt-4o-mini",
            max_tokens=4096,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content

    elif AI_PROVIDER == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=AI_API_KEY)
        model = genai.GenerativeModel(AI_MODEL or "gemini-1.5-flash", system_instruction=SYSTEM_PROMPT)
        return model.generate_content(prompt).text

    else:
        raise ValueError(f"지원하지 않는 AI: {AI_PROVIDER}")


def extract_principles(transcripts: dict[str, str]) -> list[dict]:
    print(f"\n[3/3] AI 투자 원칙 분석 중 ({AI_PROVIDER}/{AI_MODEL})...")
    print(f"  총 자막: {sum(len(v) for v in transcripts.values()):,}자")

    if not AI_API_KEY:
        print("  [오류] AI API 키가 없습니다. .env 파일에 AI_API_KEY를 설정하세요.")
        sys.exit(1)

    # 배치 분할 (60,000자씩)
    BATCH_SIZE = 60_000
    batches = []
    current = []
    current_size = 0

    for vid, text in transcripts.items():
        chunk = f"\n[영상 {vid}]\n{text[:3000]}\n"  # 영상당 최대 3000자
        if current_size + len(chunk) > BATCH_SIZE and current:
            batches.append("\n".join(current))
            current = [chunk]
            current_size = len(chunk)
        else:
            current.append(chunk)
            current_size += len(chunk)
    if current:
        batches.append("\n".join(current))

    print(f"  {len(batches)}개 배치로 분할 처리")

    all_principles = []
    channel_styles = []

    for i, batch in enumerate(batches):
        print(f"  배치 {i+1}/{len(batches)} 분석 중... ", end="", flush=True)

        prompt = f"""다음은 YouTube 주식 투자 채널 영상들의 자막입니다.
이 유튜버가 반복적으로 강조하는 투자 원칙, 종목 선택 기준, 매수/매도 타이밍을 추출하세요.
반드시 영상 내용에 실제로 언급된 내용만 추출하세요.

자막:
{batch}"""

        try:
            response = _call_ai(prompt)

            # JSON 추출
            clean = response.strip()
            if "```" in clean:
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
                clean = clean.strip()

            data = json.loads(clean)
            batch_principles = data.get("principles", [])
            style = data.get("channel_style", "")

            all_principles.extend(batch_principles)
            if style:
                channel_styles.append(style)
            print(f"{len(batch_principles)}개 원칙 추출")

        except json.JSONDecodeError as e:
            print(f"JSON 파싱 오류: {e}")
        except Exception as e:
            print(f"오류: {e}")

        time.sleep(1)  # API rate limit

    # 중복 제거 (제목 기준)
    seen = {}
    merged = []
    for p in all_principles:
        title = p.get("title", "").strip()
        if title and title not in seen:
            seen[title] = True
            p["id"] = f"P{len(merged)+1:03d}"
            merged.append(p)

    # 최종 저장
    output = {
        "channel_url": CHANNEL_URL,
        "analyzed_at": datetime.now().isoformat(),
        "total_videos": len(transcripts),
        "channel_style": " / ".join(channel_styles),
        "principles": merged,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PRINCIPLES_OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    return merged


# ══════════════════════════════════════════════════════════════════════════════
# 결과 출력
# ══════════════════════════════════════════════════════════════════════════════

def print_results(principles: list[dict], channel_style: str):
    SEP = "=" * 60
    print(f"\n{SEP}")
    print("  📋 투자 원칙 분석 결과")
    print(f"  채널: {CHANNEL_URL}")
    print(SEP)
    print(f"\n채널 투자 스타일:\n  {channel_style}\n")

    cats = {}
    for p in principles:
        cat = p.get("category", "기타")
        cats.setdefault(cat, []).append(p)

    for cat, items in cats.items():
        print(f"\n【{cat}】")
        for p in items:
            print(f"  [{p['id']}] {p['title']}")
            print(f"       {p.get('description', '')}")
            conds = p.get("conditions", [])
            if conds:
                print(f"       조건: {' / '.join(conds[:2])}")
            evidence = p.get("evidence", "")
            if evidence:
                print(f"       근거: \"{evidence}\"")

    print(f"\n{SEP}")
    print(f"총 {len(principles)}개 원칙 추출 완료")
    print(f"저장 위치: {PRINCIPLES_OUTPUT}")
    print(SEP)


# ══════════════════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print(f"  유튜브 채널 투자 원칙 분석기")
    print(f"  채널: {CHANNEL_URL}")
    print(f"  AI:   {AI_PROVIDER} / {AI_MODEL}")
    print("=" * 60)

    if not AI_API_KEY and AI_PROVIDER != "ollama":
        print(f"\n[오류] API 키 없음. .env 파일에 AI_API_KEY={AI_PROVIDER} 키를 입력하세요.")
        sys.exit(1)

    # Step 1: 영상 목록
    videos = get_video_ids(CHANNEL_URL)
    if not videos:
        print("영상을 찾을 수 없습니다. URL을 확인하세요.")
        sys.exit(1)

    # Step 2: 자막 수집
    transcripts = get_transcripts(videos)
    if not transcripts:
        print("자막을 가져올 수 없습니다. 채널에 자막이 없을 수 있습니다.")
        sys.exit(1)

    # Step 3: AI 분석
    principles = extract_principles(transcripts)

    # 결과 출력
    result_data = json.loads(PRINCIPLES_OUTPUT.read_text(encoding="utf-8"))
    print_results(principles, result_data.get("channel_style", ""))
