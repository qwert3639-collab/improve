@echo off
chcp 65001
echo ================================================
echo  주식 분석 프로그램 - 패키지 설치
echo  (64비트 Python, HTS 불필요)
echo ================================================
echo.

python --version 2>NUL
if errorlevel 1 (
    echo [오류] Python이 설치되지 않았습니다.
    echo https://www.python.org/downloads/ 에서 Python 3.11 64비트를 설치하세요.
    pause
    exit /b 1
)

echo [1/5] pip 업그레이드 중...
python -m pip install --upgrade pip

echo.
echo [2/5] Claude API 설치 중...
pip install anthropic

echo.
echo [3/5] YouTube 도구 설치 중...
pip install yt-dlp
pip install youtube-transcript-api

echo.
echo [4/5] PyQt5 UI 라이브러리 설치 중...
pip install PyQt5

echo.
echo [5/5] KIS API 및 기타 라이브러리 설치 중...
pip install requests
pip install websockets
pip install python-dotenv

echo.
echo ================================================
echo  설치 완료!
echo ================================================
echo.
echo 다음 단계:
echo   1. https://apiportal.koreainvestment.com 에서 AppKey/AppSecret 발급
echo   2. .env.example 을 .env 로 복사 후 API 키 입력
echo   3. python main.py 실행
echo   4. 메뉴 ^> KIS API ^> API 키 설정 (또는 .env 파일로 설정)
echo.
echo [참고] 키움증권 관련 설치는 필요 없습니다.
echo        한국투자증권 REST API를 사용합니다.
echo.
pause
