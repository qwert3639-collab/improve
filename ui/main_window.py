"""
메인 윈도우
좌측 투자 원칙 패널 + 우측 실시간 추천 패널 레이아웃.
"""

import logging
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QSplitter,
    QStatusBar, QAction, QMenuBar, QMessageBox,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from ui.principle_panel import PrinciplePanel
from ui.recommendation_panel import RecommendationPanel
from engine.recommendation_engine import RecommendationEngine
from kiwoom.kiwoom_bridge import get_bridge
from config import REFRESH_INTERVAL

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """메인 애플리케이션 창"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("주식 투자 원칙 기반 종목 추천 시스템")
        self.setMinimumSize(1200, 700)
        self.resize(1400, 800)

        self._engine = RecommendationEngine()
        self._kiwoom_connected = False
        self._refresh_timer = QTimer(self)

        self._setup_ui()
        self._setup_menu()
        self._setup_connections()
        self._try_connect_kiwoom()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # 좌우 분할
        splitter = QSplitter(Qt.Horizontal)

        # 좌측: 투자 원칙 패널
        self.principle_panel = PrinciplePanel()
        self.principle_panel.setMinimumWidth(350)
        self.principle_panel.setMaximumWidth(500)
        splitter.addWidget(self.principle_panel)

        # 우측: 추천 패널
        self.rec_panel = RecommendationPanel()
        splitter.addWidget(self.rec_panel)

        splitter.setSizes([380, 1020])
        main_layout.addWidget(splitter)

        # 상태바
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("시작 중...")

    def _setup_menu(self):
        menubar = self.menuBar()

        # 파일 메뉴
        file_menu = menubar.addMenu("파일")

        exit_action = QAction("종료", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 키움 메뉴
        kiwoom_menu = menubar.addMenu("키움 API")

        connect_action = QAction("키움 연결", self)
        connect_action.triggered.connect(self._try_connect_kiwoom)
        kiwoom_menu.addAction(connect_action)

        disconnect_action = QAction("연결 해제", self)
        disconnect_action.triggered.connect(self._disconnect_kiwoom)
        kiwoom_menu.addAction(disconnect_action)

        # 도움말 메뉴
        help_menu = menubar.addMenu("도움말")
        about_action = QAction("사용 방법", self)
        about_action.triggered.connect(self._show_help)
        help_menu.addAction(about_action)

    def _setup_connections(self):
        # 원칙 패널 → 추천 엔진 채널 URL 업데이트
        self.principle_panel.principles_updated.connect(self._on_principles_updated)

        # 수동 갱신 버튼
        self.rec_panel.refresh_btn.clicked.connect(self._manual_refresh)

        # 추천 엔진 콜백 등록
        self._engine.set_callbacks(
            on_update=self._on_recommendations_updated,
            on_error=self._on_engine_error,
        )

        # 실시간 갱신 타이머
        self._refresh_timer.timeout.connect(self._auto_refresh)
        self._refresh_timer.start(REFRESH_INTERVAL * 1000)

    def _try_connect_kiwoom(self):
        """키움 API 연결 시도"""
        self.status_bar.showMessage("키움 API 연결 중...")
        bridge = get_bridge()

        if bridge.ping():
            self._kiwoom_connected = True
            self.status_bar.showMessage("키움 API 연결됨 ✓")
            self.rec_panel.set_status("키움 API 연결됨. 원칙 분석 후 추천 시작됩니다.")
            self._engine.load_principles()
            if self._engine.principles:
                self._engine.start()
        else:
            # 서버 시작 시도
            self.status_bar.showMessage("키움 서버 시작 중... (최대 30초 소요)")
            success = bridge.start_server()
            if success:
                self._kiwoom_connected = True
                self.status_bar.showMessage("키움 API 연결됨 ✓")
                self.rec_panel.set_status("키움 API 연결됨.")
                self._engine.load_principles()
                if self._engine.principles:
                    self._engine.start()
            else:
                self._kiwoom_connected = False
                msg = (
                    "키움 API에 연결할 수 없습니다.\n\n"
                    "확인사항:\n"
                    "1. 키움증권 OpenAPI+ 설치 완료\n"
                    "2. HTS 실행 및 로그인 상태\n"
                    "3. setup/install_32bit.bat 실행 완료\n"
                    "4. 32비트 Python 설치 확인\n\n"
                    "유튜브 채널 분석은 키움 연결 없이도 사용 가능합니다."
                )
                self.status_bar.showMessage("키움 API 연결 실패")
                self.rec_panel.set_status("키움 연결 필요 (메뉴 → 키움 API → 연결)", is_error=True)
                QMessageBox.warning(self, "키움 연결 실패", msg)

    def _disconnect_kiwoom(self):
        """키움 연결 해제"""
        self._engine.stop()
        bridge = get_bridge()
        bridge.stop_server()
        self._kiwoom_connected = False
        self.status_bar.showMessage("키움 API 연결 해제됨")
        self.rec_panel.set_status("키움 연결 해제됨")

    def _on_principles_updated(self, principles: list):
        """원칙 분석 완료 시"""
        channel_url = self.principle_panel.url_input.text().strip()
        self._engine.channel_url = channel_url
        self._engine.principles = principles

        if self._kiwoom_connected and principles:
            if not self._engine._running:
                self._engine.start()
            self.status_bar.showMessage(f"원칙 {len(principles)}개 로드 완료. 실시간 추천 시작.")
        elif principles:
            self.status_bar.showMessage(f"원칙 {len(principles)}개 로드 완료. 키움 연결 후 추천 가능.")

    def _on_recommendations_updated(self, recommendations: list):
        """추천 결과 갱신"""
        self.rec_panel.update_recommendations(recommendations)

    def _on_engine_error(self, message: str):
        """추천 엔진 오류"""
        self.rec_panel.set_status(f"오류: {message}", is_error=True)
        logger.error(f"추천 엔진 오류: {message}")

    def _auto_refresh(self):
        """자동 갱신 (타이머)"""
        if self._engine.current_recommendations:
            self.rec_panel.update_recommendations(self._engine.current_recommendations)

    def _manual_refresh(self):
        """수동 갱신 버튼"""
        if not self._kiwoom_connected:
            QMessageBox.information(self, "알림", "키움 API가 연결되지 않았습니다.")
            return
        self.rec_panel.set_status("갱신 중...")
        # 다음 루프 주기를 기다리지 않고 즉시 표시
        recs = self._engine.get_recommendations()
        if recs:
            self.rec_panel.update_recommendations(recs)

    def _show_help(self):
        help_text = """【사용 방법】

1. 채널 분석
   - 좌측 '채널 URL' 입력란에 유튜브 채널 주소 입력
   - '채널 분석 시작' 클릭 → 영상 자막 수집 및 AI 분석
   - 완료 시 좌측에 투자 원칙 목록 표시

2. 종목 추천
   - 키움증권 HTS 실행 및 로그인 상태 유지
   - 우측 테이블에 원칙에 부합하는 종목 실시간 표시
   - 종목 더블클릭 → 추천 이유 상세 확인

3. 매매
   - 이 프로그램은 매매를 직접 실행하지 않습니다
   - 추천 종목 확인 후 키움 HTS/MTS에서 직접 매매하세요

【주의사항】
- 이 프로그램의 추천은 참고용이며, 투자 손실에 대한 책임은 사용자에게 있습니다.
- 키움 OpenAPI는 실제 주식시장 운영 시간(09:00~15:30)에만 시세 제공됩니다.
"""
        QMessageBox.information(self, "사용 방법", help_text)

    def closeEvent(self, event):
        """창 닫힐 때 정리"""
        self._engine.stop()
        bridge = get_bridge()
        bridge.stop_server()
        event.accept()
