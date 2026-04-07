"""
설정 파일 - API 키 및 전역 설정값
실제 사용 시 ANTHROPIC_API_KEY와 CHANNEL_URL을 입력하세요.
"""

import os

# ─── Claude API ────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "여기에_Claude_API_키_입력")
CLAUDE_MODEL = "claude-sonnet-4-6"

# ─── YouTube ────────────────────────────────────────────────────────────────────
# 분석할 유튜브 채널 URL (채널 홈 또는 /videos 탭 URL)
DEFAULT_CHANNEL_URL = ""  # 예: "https://www.youtube.com/@채널명/videos"

# 채널당 최대 분석 영상 수 (0 = 전체)
MAX_VIDEOS = 0

# 자막 언어 우선순위
TRANSCRIPT_LANGUAGES = ["ko", "ko-KR"]

# ─── 데이터베이스 ────────────────────────────────────────────────────────────────
import pathlib
BASE_DIR = pathlib.Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "principles.db"
CACHE_DIR = DATA_DIR / "cache"

# ─── 키움 브릿지 소켓 ──────────────────────────────────────────────────────────
KIWOOM_HOST = "127.0.0.1"
KIWOOM_PORT = 9999
KIWOOM_TIMEOUT = 10  # 초

# ─── 추천 엔진 ──────────────────────────────────────────────────────────────────
# 실시간 갱신 주기 (초)
REFRESH_INTERVAL = 5

# 추천 종목 최대 표시 수
MAX_RECOMMENDATIONS = 10

# 스크리닝 대상 시장 ("KOSPI", "KOSDAQ", "ALL")
TARGET_MARKET = "ALL"

# 최소 거래대금 필터 (원) - 너무 소형주 제외
MIN_TRADE_AMOUNT = 1_000_000_000  # 10억원

# ─── Claude 분석 프롬프트 ────────────────────────────────────────────────────────
PRINCIPLE_EXTRACTION_SYSTEM_PROMPT = """당신은 주식 투자 전문가입니다.
주식 투자 유튜버의 영상 스크립트를 분석하여 해당 유튜버의 투자 철학과 원칙을 체계적으로 추출합니다.

출력 형식은 반드시 다음 JSON 구조를 따르세요:
{
  "principles": [
    {
      "id": "P001",
      "category": "종목선택 | 매수시점 | 매도시점 | 리스크관리 | 시장분석 | 기타",
      "title": "원칙 제목 (20자 이내)",
      "description": "상세 설명 (100자 이내)",
      "conditions": ["조건1", "조건2"],
      "indicators": ["사용하는 지표1", "지표2"],
      "keywords": ["관련 키워드"]
    }
  ],
  "summary": "이 유튜버의 전체 투자 스타일 요약 (200자 이내)"
}"""

PRINCIPLE_EXTRACTION_USER_PROMPT = """다음은 주식 투자 유튜버의 영상 스크립트 모음입니다.
이 유튜버가 반복적으로 강조하는 투자 원칙, 종목 선택 기준, 매수/매도 시점, 리스크 관리 방법을 추출하세요.

스크립트:
{transcripts}

위 내용에서 투자 원칙을 JSON 형식으로 추출하세요."""

STOCK_RECOMMENDATION_PROMPT = """당신은 주식 투자 분석가입니다.
다음 투자 원칙과 현재 종목 데이터를 바탕으로, 각 종목이 투자 원칙에 얼마나 부합하는지 분석하세요.

투자 원칙:
{principles}

종목 데이터:
{stock_data}

각 종목에 대해 다음을 평가하세요:
1. 어떤 원칙에 해당하는지
2. 매수 추천 여부와 이유
3. 0-100점 사이의 적합도 점수

JSON 형식으로 출력하세요:
{
  "recommendations": [
    {
      "code": "종목코드",
      "name": "종목명",
      "score": 85,
      "matched_principles": ["P001", "P003"],
      "reason": "추천 이유 상세 설명",
      "action": "BUY | WATCH | SKIP",
      "caution": "주의사항 (있을 경우)"
    }
  ]
}"""
