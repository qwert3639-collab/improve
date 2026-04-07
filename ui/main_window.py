"""
메인 윈도우 (KIS API 버전)
좌측 투자 원칙 패널 + 우측 실시간 추천 패널 레이아웃.
"""

import logging
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QSplitter,
    QStatusBar, QAction, QMenuBar, QMessageBox, QInputDialog, QLineEdit,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from ui.principle_panel import PrinciplePanel
from ui.recommendation_panel import RecommendationPanel
from engine.recommendation_engine import RecommendationEngine
from kis.kis_client import get_client
from kis.kis_auth import get_auth
from config import REFRESH_INTERVAL, KIS_IS_VIRTUAL

logger = logging.getLogger(__name__)

# AI 분석 보고서 팝업 표시 여부 (True: 매번 표시, False: 테이블만 갱신)
SHOW_ANALYSIS_REPORT = True

class MainWindow(QMainWindow):
    """메인 애플리케이션 창"""

    def __init__(self):
        super().__init__()
        env_tag = "[모의투자]" if KIS_IS_VIRTUAL else "[실전투자]"
        self.setWindowTitle(f"주식 투자 원칙 기반 종목 추천 시스템 {env_tag}")
        self.setMinimumSize(1200, 700)
        self.resize(1400, 800)

        self._engine = RecommendationEngine()
        self._kis_connected = False
        self._refresh_timer = QTimer(self)

        self._setup_ui()
        self._setup_menu()
        self._setup_connections()
        self._try_connect_kis()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Horizontal)

        self.principle_panel = PrinciplePanel()
        self.principle_panel.setMinimumWidth(350)
        self.principle_panel.setMaximumWidth(500)
        splitter.addWidget(self.principle_panel)

        self.rec_panel = RecommendationPanel()
        splitter.addWidget(self.rec_panel)

        splitter.setSizes([380, 1020])
        main_layout.addWidget(splitter)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("시작 중...")

    def _setup_menu(self):
        menubar = self.menuBar()

        # 파일
        file_menu = menubar.addMenu("파일")
        exit_action = QAction("종료", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # KIS API
        kis_menu = menubar.addMenu("KIS API")

        connect_action = QAction("연결 확인", self)
        connect_action.triggered.connect(self._try_connect_kis)
        kis_menu.addAction(connect_action)

        set_key_action = QAction("API 키 설정...", self)
        set_key_action.triggered.connect(self._show_api_key_dialog)
        kis_menu.addAction(set_key_action)

        kis_menu.addSeparator()

        mode_label = "현재: 모의투자 모드" if KIS_IS_VIRTUAL else "현재: 실전투자 모드"
        mode_action = QAction(mode_label, self)
        mode_action.setEnabled(False)
        kis_menu.addAction(mode_action)

        # 설정
        settings_menu = menubar.addMenu("설정")
        settings_action = QAction("API 키 설정 (AI + KIS)...", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._show_settings)
        settings_menu.addAction(settings_action)

        # 도움말
        help_menu = menubar.addMenu("도움말")
        about_action = QAction("사용 방법", self)
        about_action.triggered.connect(self._show_help)
        help_menu.addAction(about_action)

        setup_action = QAction("KIS API 설정 안내", self)
        setup_action.triggered.connect(self._show_kis_setup_guide)
        help_menu.addAction(setup_action)

    def _setup_connections(self):
        self.principle_panel.principles_updated.connect(self._on_principles_updated)
        self.rec_panel.refresh_btn.clicked.connect(self._manual_refresh)

        self._engine.set_callbacks(
            on_update=self._on_recommendations_updated,
            on_error=self._on_engine_error,
        )

        self._refresh_timer.timeout.connect(self._auto_refresh)
        self._refresh_timer.start(REFRESH_INTERVAL * 1000)

    def _try_connect_kis(self):
        """KIS API 연결 테스트"""
        self.status_bar.showMessage("KIS API 연결 확인 중...")
        self.rec_panel.set_status("KIS API 연결 확인 중...")

        try:
            auth = get_auth()
            if not auth.is_valid():
                self._kis_connected = False
                self.status_bar.showMessage("KIS API 키 오류")
                self.rec_panel.set_status("API 키를 설정하세요 (메뉴 → KIS API → API 키 설정)", is_error=True)
                return

            client = get_client()
            if client.verify_connection():
                self._kis_connected = True
                env_str = "모의투자" if KIS_IS_VIRTUAL else "실전투자"
                self.status_bar.showMessage(f"KIS API 연결됨 [{env_str}] ✓")
                self.rec_panel.set_status(f"KIS API 연결됨 [{env_str}]. 채널 분석 후 추천이 시작됩니다.")

                self._engine.load_principles()
                if self._engine.principles:
                    self._engine.start()
            else:
                self._kis_connected = False
                self.status_bar.showMessage("KIS API 연결 실패")
                self.rec_panel.set_status(
                    "KIS API 연결 실패. AppKey/AppSecret을 확인하세요.", is_error=True
                )

        except RuntimeError as e:
            self._kis_connected = False
            self.status_bar.showMessage("KIS API 키 없음")
            self.rec_panel.set_status(str(e), is_error=True)
            QMessageBox.warning(self, "KIS API 설정 필요", str(e) + "\n\n메뉴 → KIS API → API 키 설정")

    def _show_settings(self):
        """통합 설정 다이얼로그"""
        from ui.settings_panel import SettingsDialog
        dialog = SettingsDialog(self)
        dialog.settings_saved.connect(self._try_connect_kis)
        dialog.exec_()

    def _show_api_key_dialog(self):
        """API 키 입력 다이얼로그"""
        import config

        app_key, ok1 = QInputDialog.getText(
            self, "KIS AppKey 입력",
            "KIS Developers에서 발급받은 AppKey를 입력하세요:",
            QLineEdit.Normal, config.KIS_APP_KEY if "여기에" not in config.KIS_APP_KEY else "",
        )
        if not ok1 or not app_key.strip():
            return

        app_secret, ok2 = QInputDialog.getText(
            self, "KIS AppSecret 입력",
            "AppSecret을 입력하세요:",
            QLineEdit.Password, "",
        )
        if not ok2 or not app_secret.strip():
            return

        # 런타임 설정 적용
        config.KIS_APP_KEY = app_key.strip()
        config.KIS_APP_SECRET = app_secret.strip()

        # auth 인스턴스 갱신
        import kis.kis_auth as kis_auth_module
        kis_auth_module._auth_instance = None

        # .env 파일에 저장
        env_path = __import__("pathlib").Path(__file__).parent.parent / ".env"
        lines = []
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()

        def update_or_add(lines, key, value):
            updated = False
            for i, line in enumerate(lines):
                if line.startswith(f"{key}="):
                    lines[i] = f"{key}={value}"
                    updated = True
                    break
            if not updated:
                lines.append(f"{key}={value}")
            return lines

        lines = update_or_add(lines, "KIS_APP_KEY", app_key.strip())
        lines = update_or_add(lines, "KIS_APP_SECRET", app_secret.strip())
        env_path.write_text("\n".join(lines), encoding="utf-8")

        QMessageBox.information(self, "저장 완료", "API 키가 .env 파일에 저장되었습니다.\n연결을 다시 시도합니다.")
        self._try_connect_kis()

    def _on_principles_updated(self, principles: list):
        """원칙 분석 완료 시"""
        channel_url = self.principle_panel.url_input.text().strip()
        self._engine.channel_url = channel_url
        self._engine.principles = principles

        if self._kis_connected and principles:
            if not self._engine._running:
                self._engine.start()
            self.status_bar.showMessage(f"원칙 {len(principles)}개 로드. 실시간 추천 시작.")
        elif principles:
            self.status_bar.showMessage(f"원칙 {len(principles)}개 로드. KIS 연결 후 추천 가능.")

    def _on_recommendations_updated(self, recommendations: list):
        self.rec_panel.update_recommendations(recommendations)

        # AI가 새로 분석한 결과(source != "rule")이면 보고서 팝업
        if SHOW_ANALYSIS_REPORT and recommendations:
            ai_recs = [r for r in recommendations if r.get("source") != "rule"]
            if ai_recs and hasattr(self._engine, "_last_report_shown"):
                import time
                # 같은 AI 결과를 중복 팝업하지 않도록 타임스탬프 비교
                if time.time() - self._engine._last_report_shown < 5:
                    return
            if ai_recs:
                self._show_analysis_report(recommendations)

    def _on_engine_error(self, message: str):
        self.rec_panel.set_status(f"오류: {message}", is_error=True)
        logger.error(f"추천 엔진 오류: {message}")

    def _auto_refresh(self):
        if self._engine.current_recommendations:
            self.rec_panel.update_recommendations(self._engine.current_recommendations)

    def _manual_refresh(self):
        if not self._kis_connected:
            QMessageBox.information(self, "알림", "KIS API가 연결되지 않았습니다.\n메뉴 → KIS API → 연결 확인")
            return
        recs = self._engine.get_recommendations()
        if recs:
            self.rec_panel.update_recommendations(recs)
        else:
            self.rec_panel.set_status("추천 데이터 없음. 채널 분석을 먼저 진행하세요.")

    def _show_analysis_report(self, recommendations: list):
        """분석 보고서 팝업"""
        import time
        from ui.analysis_report_dialog import show_analysis_report
        self._engine._last_report_shown = time.time()
        show_analysis_report(
            recommendations,
            self._engine.principles,
            parent=self,
        )

    def _show_help(self):
        help_text = """【사용 방법】

1. KIS API 설정 (최초 1회)
   - 메뉴 → KIS API → API 키 설정
   - KIS Developers(apiportal.koreainvestment.com)에서 발급

2. 채널 분석
   - 좌측 채널 URL 입력 → '채널 분석 시작'
   - AI가 투자 원칙 자동 추출 (수분 소요)

3. 종목 추천 확인
   - 우측 테이블에 원칙 부합 종목 실시간 표시
   - 종목 더블클릭 → 추천 이유 상세 확인

4. 매매
   - 이 프로그램은 매매를 실행하지 않습니다
   - 한국투자증권 앱/HTS에서 직접 주문하세요

【주의사항】
- 처음에는 반드시 '모의투자' 모드로 테스트하세요 (config.py: KIS_IS_VIRTUAL=True)
- 이 프로그램의 추천은 참고용입니다. 투자 손실 책임은 사용자에게 있습니다.
- KIS API는 장 시간(09:00~15:30)에 실시간 데이터가 제공됩니다.
"""
        QMessageBox.information(self, "사용 방법", help_text)

    def _show_kis_setup_guide(self):
        guide = """【KIS Developers API 설정 안내】

1. 한국투자증권 계좌 개설
   - 한국투자증권 앱 또는 영업점에서 개설

2. KIS Developers 가입
   - https://apiportal.koreainvestment.com 접속
   - 회원가입 및 로그인

3. AppKey/AppSecret 발급
   - '앱 관리' → '앱 추가' → 서비스 신청
   - 발급된 AppKey와 AppSecret을 복사

4. 모의투자 설정 (권장)
   - config.py 파일에서 KIS_IS_VIRTUAL = True 확인
   - 모의투자로 충분히 테스트 후 실전투자 전환

5. 이 프로그램에 입력
   - 메뉴 → KIS API → API 키 설정
   - AppKey, AppSecret 입력 후 저장

참고: 실전투자 전환 시 config.py에서
      KIS_IS_VIRTUAL = False 로 변경
"""
        QMessageBox.information(self, "KIS API 설정 안내", guide)

    def closeEvent(self, event):
        self._engine.stop()
        event.accept()
