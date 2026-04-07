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


def check_api_key():
    """Claude API 키 확인"""
    from config import ANTHROPIC_API_KEY

    if not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY == "여기에_Claude_API_키_입력":
        # .env 파일에서 로드 시도
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            try:
                from dotenv import load_dotenv
                load_dotenv(env_path)
                import config
                config.ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
                if config.ANTHROPIC_API_KEY:
                    logger.info("API 키를 .env 파일에서 로드했습니다.")
                    return
            except Exception:
                pass

        # 환경변수 확인
        env_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if env_key:
            import config
            config.ANTHROPIC_API_KEY = env_key
            logger.info("API 키를 환경변수에서 로드했습니다.")
            return

        print("=" * 60)
        print("[경고] Claude API 키가 설정되지 않았습니다.")
        print()
        print("설정 방법 (둘 중 하나):")
        print("  1. config.py 파일의 ANTHROPIC_API_KEY 수정")
        print("  2. 프로젝트 루트에 .env 파일 생성:")
        print("     ANTHROPIC_API_KEY=sk-ant-...")
        print()
        print("API 키 없이는 채널 분석 및 AI 추천 기능을 사용할 수 없습니다.")
        print("=" * 60)


def main():
    logger.info("=" * 50)
    logger.info("주식 투자 원칙 기반 종목 추천 시스템 시작")
    logger.info("=" * 50)

    # 필수 패키지 확인
    check_requirements()

    # API 키 확인
    check_api_key()

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
