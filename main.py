"""
주식 투자 원칙 기반 종목 추천 시스템
메인 진입점 (64비트 Python으로 실행)

실행 방법:
  python main.py

키움 OpenAPI는 setup/install_32bit.bat 설치 후 자동 연결됩니다.
"""

import sys
import os
import logging
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent))

# 로그 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def check_requirements():
    """필수 패키지 설치 확인"""
    missing = []
    packages = {
        "anthropic": "anthropic",
        "yt_dlp": "yt-dlp",
        "youtube_transcript_api": "youtube-transcript-api",
        "PyQt5": "PyQt5",
        "requests": "requests",
        "websockets": "websockets",
    }
    for module, pkg in packages.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(pkg)

    if missing:
        print("=" * 60)
        print("[오류] 다음 패키지가 설치되지 않았습니다:")
        for p in missing:
            print(f"  - {p}")
        print()
        print("해결 방법: setup/install_64bit.bat 실행")
        print("=" * 60)
        sys.exit(1)


def load_env_keys():
    """
    .env 파일 또는 환경변수에서 API 키를 로드합니다.
    config.py의 기본값보다 .env 파일이 우선합니다.
    """
    import config

    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path, override=True)
            logger.info(".env 파일 로드 완료")
        except ImportError:
            # dotenv 없으면 수동 파싱
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())

    # Claude API 키
    claude_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if claude_key and "여기에" not in claude_key:
        config.ANTHROPIC_API_KEY = claude_key

    # KIS API 키
    kis_key = os.environ.get("KIS_APP_KEY", "")
    kis_secret = os.environ.get("KIS_APP_SECRET", "")
    if kis_key and "여기에" not in kis_key:
        config.KIS_APP_KEY = kis_key
    if kis_secret and "여기에" not in kis_secret:
        config.KIS_APP_SECRET = kis_secret

    # 경고 출력
    missing = []
    if not claude_key or "여기에" in config.ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY (Claude AI 분석용)")
    if not kis_key or "여기에" in config.KIS_APP_KEY:
        missing.append("KIS_APP_KEY / KIS_APP_SECRET (시세 조회용)")

    if missing:
        print("=" * 60)
        print("[안내] 다음 API 키가 설정되지 않았습니다:")
        for m in missing:
            print(f"  - {m}")
        print()
        print(".env 파일에 입력하거나, 실행 후 메뉴에서 설정 가능합니다.")
        print("=" * 60)


def main():
    logger.info("=" * 50)
    logger.info("주식 투자 원칙 기반 종목 추천 시스템 시작")
    logger.info("=" * 50)

    # 필수 패키지 확인
    check_requirements()

    # .env / 환경변수에서 API 키 로드
    load_env_keys()

    # data 디렉토리 생성
    from config import DATA_DIR, CACHE_DIR
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # PyQt5 앱 시작
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    from ui.main_window import MainWindow

    # 고DPI 스케일링 활성화 (4K 모니터 지원)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("주식 종목 추천 시스템")
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    logger.info("UI 시작 완료")
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
