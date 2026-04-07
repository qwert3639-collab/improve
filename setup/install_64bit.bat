@echo off
chcp 65001
echo ================================================
echo  주식 분석 프로그램 - 64비트 패키지 설치
echo ================================================
echo.

REM Python 64비트가 설치되어 있는지 확인
python --version 2>NUL
if errorlevel 1 (
    echo [오류] Python이 설치되지 않았습니다.
    echo https://www.python.org/downloads/ 에서 Python 3.11 64비트를 설치하세요.
    pause
    exit /b 1
)

echo [1/6] pip 업그레이드 중...
python -m pip install --upgrade pip

echo.
echo [2/6] Claude API 설치 중...
pip install anthropic

echo.
echo [3/6] YouTube 도구 설치 중...
pip install yt-dlp
pip install youtube-transcript-api

echo.
echo [4/6] PyQt5 UI 라이브러리 설치 중...
pip install PyQt5
pip install PyQtWebEngine

echo.
echo [5/6] 기타 라이브러리 설치 중...
pip install requests
pip install python-dotenv

echo.
echo [6/6] yt-dlp 실행 파일 확인 중...
yt-dlp --version 2>NUL
if errorlevel 1 (
    echo yt-dlp 명령어를 PATH에 추가하는 중...
    python -m pip install yt-dlp
)

echo.
echo ================================================
echo  설치 완료!
echo ================================================
echo.
echo 다음 단계:
echo   1. setup\install_32bit.bat 실행 (키움 API용)
echo   2. config.py 파일에 API 키 입력
echo   3. python main.py 실행
echo.
pause
