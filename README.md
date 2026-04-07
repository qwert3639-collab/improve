# 주식 투자 원칙 기반 종목 추천 시스템

유튜브 주식 채널의 모든 영상을 AI로 분석하여 투자 원칙을 추출하고,
키움증권 OpenAPI와 연동하여 실시간으로 종목을 추천하는 프로그램입니다.

> **자동 매매 없음** — 추천 확인 후 사용자가 직접 HTS에서 매매합니다.

---

## 📋 설치 순서

### 1. Python 64비트 설치
- https://www.python.org/downloads/ → Python 3.11 Windows installer (64-bit)
- 설치 시 "Add Python to PATH" 체크

### 2. Python 32비트 설치 (키움 API용)
- 동일 주소 → Python 3.8 Windows installer (32-bit / x86)

### 3. Git 설치
- https://git-scm.com/download/win

### 4. 키움증권 OpenAPI+ 설치
- https://www.kiwoom.com → 트레이딩 → Open API → 다운로드

### 5. 이 프로젝트 다운로드
```cmd
git clone https://github.com/qwert3639-collab/improve.git
cd improve
```

### 6. 패키지 설치
```cmd
setup\install_64bit.bat
setup\install_32bit.bat
```

### 7. API 키 설정
`.env.example`을 `.env`로 복사하고 API 키 입력:
```
ANTHROPIC_API_KEY=sk-ant-여기에_실제_키_입력
```

---

## 🚀 실행 방법

```cmd
python main.py
```

---

## 📖 사용 방법

### 1단계: 채널 분석
1. 좌측 '채널 URL' 입력란에 분석할 채널 주소 입력
2. '채널 분석 시작' 클릭
3. 영상 자막 수집 및 AI 분석 진행 (채널 규모에 따라 수분~수십분 소요)
4. 완료 시 좌측에 투자 원칙 목록 자동 표시

### 2단계: 종목 추천 확인
1. 키움증권 HTS 실행 및 로그인
2. 우측 테이블에 원칙 부합 종목 5초마다 갱신
3. 종목 더블클릭 → 추천 이유 상세 확인

### 3단계: 매매
- 이 프로그램은 매매를 실행하지 않습니다
- 추천 종목 확인 후 키움 HTS/MTS에서 직접 매매하세요

---

## 🏗 프로젝트 구조

```
stock-analyzer/
├── main.py                     # 진입점
├── config.py                   # 설정값
├── setup/
│   ├── install_64bit.bat       # 64비트 패키지 설치
│   └── install_32bit.bat       # 32비트 키움 패키지 설치
├── youtube/
│   ├── channel_crawler.py      # 채널 영상 목록 수집
│   ├── transcript_fetcher.py   # 자막 추출
│   └── principle_extractor.py  # Claude AI 원칙 분석
├── kiwoom/
│   ├── kiwoom_server.py        # 32비트 키움 서버
│   └── kiwoom_bridge.py        # 64비트↔32비트 소켓 브릿지
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

- **투자 책임**: 이 프로그램의 추천은 참고용입니다. 모든 투자 결정과 손실에 대한 책임은 사용자에게 있습니다.
- **키움 API 제약**: 장 시간(09:00~15:30)에만 실시간 시세 조회가 가능합니다.
- **32/64비트 분리**: 키움 OpenAPI+는 32비트 전용이므로 별도 프로세스로 실행됩니다.
- **API 비용**: Claude API 사용료가 발생합니다 (채널 분석 시 1회, 종목 추천은 1분 1회).

---

## 🔗 참고 자료

| 도구 | 링크 |
|------|------|
| 키움 Python 래퍼 (pykiwoom) | https://github.com/sharebook-kr/pykiwoom |
| yt-dlp | https://github.com/yt-dlp/yt-dlp |
| Claude API | https://docs.anthropic.com |
