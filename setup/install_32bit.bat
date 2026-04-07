@echo off
chcp 65001
echo ================================================
echo  키움 OpenAPI - 32비트 Python 패키지 설치
echo ================================================
echo.
echo [주의] 이 배치파일은 반드시 키움증권 OpenAPI+ 설치 후 실행하세요.
echo        키움증권 홈페이지 → OpenAPI → OpenAPI 다운로드
echo.

REM 32비트 Python 3.8 찾기
set PY32=
for %%v in (3.8 3.9 3.10) do (
    py -%%v-32 --version 2>NUL && set PY32=py -%%v-32 && goto :found
)

echo [오류] 32비트 Python을 찾을 수 없습니다.
echo https://www.python.org/downloads/ 에서 Python 3.8 32비트(Windows x86)를 설치하세요.
pause
exit /b 1

:found
echo [확인] 32비트 Python: %PY32%
echo.

echo [1/3] pip 업그레이드 중...
%PY32% -m pip install --upgrade pip

echo.
echo [2/3] pywin32 설치 중 (COM 인터페이스)...
%PY32% -m pip install pywin32

echo.
echo [3/3] pykiwoom 설치 중...
%PY32% -m pip install pykiwoom

echo.
echo ================================================
echo  32비트 패키지 설치 완료!
echo ================================================
echo.
echo 다음 단계:
echo   1. 키움증권 OpenAPI+ HTS에 로그인 되어 있어야 합니다.
echo   2. python main.py 실행 시 키움 서버가 자동으로 시작됩니다.
echo.
pause
