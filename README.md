# 주식 투자 원칙 기반 종목 추천 시스템

유튜브 주식 채널의 모든 영상을 AI로 분석하여 투자 원칙을 추출하고,
**한국투자증권 KIS API(REST + WebSocket)**로 실시간 종목을 추천하는 프로그램입니다.

> **자동 매매 없음** — 추천 확인 후 사용자가 직접 앱/HTS에서 매매합니다.
> **HTS 불필요** — 한국투자증권 앱 설치 없이 API 키만으로 시세 조회 가능합니다.

---

## ✅ KIS API 선택 이유

| 항목 | 키움 OpenAPI+ | 한국투자증권 KIS API |
|------|--------------|---------------------|
| HTS 필요 여부 | 반드시 실행 중이어야 함 | **불필요** |
| Python 제약 | 32비트 전용 | **64비트 자유롭게** |
| 실시간 방식 | COM 이벤트 | **WebSocket** |
| 복잡도 | 높음 (32/64 분리) | **낮음 (HTTP 호출)** |

---

## 📋 설치 순서

### 1. Python 64비트 설치
- https://www.python.org/downloads/ → Python 3.11 Windows installer (64-bit)
- 설치 시 **"Add Python to PATH"** 반드시 체크

### 2. Git 설치
- https://git-scm.com/download/win

### 3. 이 프로젝트 다운로드
```cmd
git clone https://github.com/qwert3639-collab/improve.git
cd improve
```

### 4. 패키지 설치
```cmd
setup\install_64bit.bat
```
설치되는 패키지: `anthropic`, `yt-dlp`, `youtube-transcript-api`, `PyQt5`, `requests`, `websockets`, `python-dotenv`

### 5. API 키 설정
`.env.example`을 `.env`로 복사 후 수정:
```
ANTHROPIC_API_KEY=sk-ant-실제_Claude_키
KIS_APP_KEY=실제_AppKey
KIS_APP_SECRET=실제_AppSecret
```

**KIS API 키 발급 방법:**
1. 한국투자증권 계좌 개설 (앱 또는 영업점)
2. https://apiportal.koreainvestment.com 접속 → 로그인
3. 앱 관리 → 앱 추가 → AppKey/AppSecret 발급

---

## 🚀 실행 방법

```cmd
python main.py
```

처음엔 **모의투자 모드**로 실행됩니다 (`config.py`: `KIS_IS_VIRTUAL = True`).
충분히 테스트 후 `False`로 변경하여 실전 전환.

---

## 📖 사용 방법

### 1단계: KIS API 연결
- 실행 시 자동 연결 시도
- 실패 시: 메뉴 → KIS API → API 키 설정

### 2단계: 채널 분석
1. 좌측 '채널 URL' 입력란에 유튜브 채널 주소 입력
2. '채널 분석 시작' 클릭 → AI가 투자 원칙 자동 추출 (채널 규모에 따라 수분~수십분)
3. 완료 시 좌측에 투자 원칙 목록 표시

### 3단계: 종목 추천 확인
- 우측 테이블에 원칙 부합 종목 5초마다 갱신
- 종목 더블클릭 → 추천 이유 상세 확인

### 4단계: 매매
- 이 프로그램은 매매를 실행하지 않습니다
- 추천 종목 확인 후 한국투자증권 앱/HTS에서 직접 매매하세요

---

## 🏗 프로젝트 구조

```
stock-analyzer/
├── main.py                     # 진입점
├── config.py                   # 설정값 (KIS API URL, 모델명 등)
├── setup/
│   ├── install_64bit.bat       # 패키지 설치
│   └── requirements_64bit.txt
├── youtube/
│   ├── channel_crawler.py      # 채널 영상 목록 수집 (yt-dlp)
│   ├── transcript_fetcher.py   # 자막 추출 (youtube-transcript-api)
│   └── principle_extractor.py  # Claude AI 원칙 분석
├── kis/                        # 한국투자증권 KIS API
│   ├── kis_auth.py             # 토큰 발급 및 자동 갱신
│   ├── kis_client.py           # REST API (시세, 랭킹 조회)
│   └── kis_websocket.py        # WebSocket 실시간 체결 수신
├── engine/
│   ├── recommendation_engine.py # 추천 파이프라인
│   └── stock_scorer.py         # 규칙 기반 1차 필터
└── ui/
    ├── main_window.py          # 메인 창
    ├── principle_panel.py      # 원칙 패널
    └── recommendation_panel.py # 추천 테이블
```

---

## ⚠️ 주의사항

- **모의투자 먼저**: `config.py`의 `KIS_IS_VIRTUAL = True` 상태로 충분히 테스트하세요.
- **투자 책임**: 이 프로그램의 추천은 참고용입니다. 손실에 대한 책임은 사용자에게 있습니다.
- **장 시간**: 실시간 데이터는 장 운영 시간(09:00~15:30)에만 제공됩니다.
- **API 비용**: Claude API 사용료 발생 (채널 분석 1회 약 $0.35, 이후 월 $2 이하).

---

## 🔗 참고 자료

| 도구 | 링크 |
|------|------|
| KIS Developers | https://apiportal.koreainvestment.com |
| KIS API 문서 | https://apiportal.koreainvestment.com/apiservice |
| yt-dlp | https://github.com/yt-dlp/yt-dlp |
| Claude API | https://docs.anthropic.com |
