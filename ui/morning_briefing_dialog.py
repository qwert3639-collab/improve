"""
아침 투자 정보지 다이얼로그
장 시작 전(09:00 이전) 프로그램 최초 실행 시 표시.
하루에 한 번만 표시, 확인 클릭 후 본 프로그램 시작.
"""

import logging
import threading
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextBrowser, QProgressBar, QFrame, QSizePolicy,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, QTimer
from PyQt5.QtGui import QFont, QColor, QPalette

from briefing.news_fetcher import (
    is_briefing_confirmed_today,
    mark_briefing_confirmed,
)
from briefing.briefing_generator import generate_morning_briefing

logger = logging.getLogger(__name__)


def should_show_briefing() -> bool:
    """
    아침 정보지를 표시해야 하는지 판단.
    - 오늘 아직 확인하지 않은 경우 → True
    (시간 제한 없음: 언제 켜도 오늘 첫 실행이면 표시)
    """
    return not is_briefing_confirmed_today()


class BriefingLoader(QObject):
    """백그라운드에서 찌라시를 생성하는 워커"""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def run(self):
        try:
            self.progress.emit("뉴스 및 시장 데이터 수집 중...")
            content = generate_morning_briefing()
            self.finished.emit(content)
        except Exception as e:
            logger.error(f"찌라시 생성 오류: {e}")
            self.error.emit(str(e))


class MorningBriefingDialog(QDialog):
    """
    신문 스타일 아침 투자 정보지 다이얼로그.
    확인 버튼을 누르기 전까지 메인 창이 뜨지 않음.
    """

    confirmed = pyqtSignal()  # 확인 버튼 클릭 시

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("오늘의 투자 정보지")
        self.setMinimumSize(900, 700)
        self.resize(1000, 760)
        self.setWindowFlags(Qt.Dialog | Qt.WindowMaximizeButtonHint)

        # 어두운 배경
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor("#1a1a1a"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self._setup_ui()
        self._start_loading()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 헤더 바 ────────────────────────────────────────────────────────
        header = QFrame()
        header.setStyleSheet("background: #0d0d0d; border-bottom: 2px solid #FFD700;")
        header.setFixedHeight(60)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 0, 20, 0)

        title_label = QLabel("📋  DAILY INTELLIGENCE BRIEF")
        title_label.setFont(QFont("맑은 고딕", 16, QFont.Bold))
        title_label.setStyleSheet("color: #FFD700; letter-spacing: 2px;")

        now = datetime.now()
        date_label = QLabel(now.strftime("%Y.%m.%d  %H:%M"))
        date_label.setStyleSheet("color: #888; font-size: 13px;")

        market_open = datetime.now().replace(hour=9, minute=0, second=0)
        remaining = max(0, int((market_open - now).total_seconds()))
        if remaining > 0:
            h, m = divmod(remaining // 60, 60)
            time_str = f"장 개장까지 {h}시간 {m}분" if h > 0 else f"장 개장까지 {m}분"
        else:
            time_str = "장 운영 중"
        self.countdown_label = QLabel(time_str)
        self.countdown_label.setStyleSheet("color: #FF6B35; font-size: 12px; font-weight: bold;")

        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.countdown_label)
        header_layout.addSpacing(20)
        header_layout.addWidget(date_label)
        layout.addWidget(header)

        # ── 로딩 바 (초기 표시) ────────────────────────────────────────────
        self.loading_frame = QFrame()
        self.loading_frame.setStyleSheet("background: #1a1a1a;")
        loading_layout = QVBoxLayout(self.loading_frame)
        loading_layout.setContentsMargins(40, 30, 40, 30)

        self.loading_label = QLabel("아침 시장 정보 수집 및 분석 중...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet("color: #FFD700; font-size: 14px;")

        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 0)  # 무한 진행 표시
        self.loading_bar.setStyleSheet("""
            QProgressBar {
                background: #333;
                border: 1px solid #555;
                border-radius: 4px;
                height: 8px;
            }
            QProgressBar::chunk {
                background: #FFD700;
                border-radius: 4px;
            }
        """)

        loading_layout.addStretch()
        loading_layout.addWidget(self.loading_label)
        loading_layout.addSpacing(12)
        loading_layout.addWidget(self.loading_bar)
        loading_layout.addStretch()
        layout.addWidget(self.loading_frame)

        # ── 본문 (로딩 후 표시) ────────────────────────────────────────────
        self.content_browser = QTextBrowser()
        self.content_browser.setStyleSheet("""
            QTextBrowser {
                background: #1a1a1a;
                border: none;
                font-size: 13px;
            }
            QScrollBar:vertical {
                background: #2a2a2a;
                width: 10px;
            }
            QScrollBar::handle:vertical {
                background: #555;
                border-radius: 5px;
            }
        """)
        self.content_browser.setVisible(False)
        self.content_browser.setOpenExternalLinks(True)
        layout.addWidget(self.content_browser, 1)

        # ── 하단 바 ────────────────────────────────────────────────────────
        footer = QFrame()
        footer.setStyleSheet("background: #0d0d0d; border-top: 1px solid #333;")
        footer.setFixedHeight(60)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(20, 0, 20, 0)

        disclaimer = QLabel(
            "⚠ 이 정보지는 AI가 공개 데이터를 분석한 참고 자료입니다. 투자 결정은 본인 책임입니다."
        )
        disclaimer.setStyleSheet("color: #666; font-size: 11px;")

        self.refresh_btn = QPushButton("🔄 재생성")
        self.refresh_btn.setFixedWidth(90)
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setStyleSheet(
            "QPushButton { background: #333; color: #aaa; border: 1px solid #555; "
            "border-radius: 4px; padding: 6px; }"
            "QPushButton:hover { background: #444; }"
        )
        self.refresh_btn.clicked.connect(self._regenerate)

        self.confirm_btn = QPushButton("✓  확인하고 시작")
        self.confirm_btn.setFixedWidth(150)
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.setFont(QFont("맑은 고딕", 12, QFont.Bold))
        self.confirm_btn.setStyleSheet("""
            QPushButton {
                background: #FFD700;
                color: #000;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
            }
            QPushButton:hover { background: #FFC000; }
            QPushButton:disabled { background: #555; color: #888; }
        """)
        self.confirm_btn.clicked.connect(self._on_confirmed)

        footer_layout.addWidget(disclaimer)
        footer_layout.addStretch()
        footer_layout.addWidget(self.refresh_btn)
        footer_layout.addSpacing(10)
        footer_layout.addWidget(self.confirm_btn)
        layout.addWidget(footer)

        # 카운트다운 타이머
        self._countdown_timer = QTimer(self)
        self._countdown_timer.timeout.connect(self._update_countdown)
        self._countdown_timer.start(60000)  # 1분마다 갱신

    def _start_loading(self):
        """백그라운드에서 찌라시 생성 시작"""
        self._thread = QThread()
        self._worker = BriefingLoader()
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_loaded)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)

        self._thread.start()

    def _on_progress(self, message: str):
        self.loading_label.setText(message)

    def _on_loaded(self, content: str):
        """찌라시 로드 완료"""
        self.loading_frame.setVisible(False)
        self.content_browser.setVisible(True)
        self.content_browser.setHtml(content)
        self.confirm_btn.setEnabled(True)
        self.refresh_btn.setEnabled(True)

    def _on_error(self, message: str):
        """오류 발생 시 기본 내용 표시"""
        self.loading_frame.setVisible(False)
        self.content_browser.setVisible(True)
        self.content_browser.setHtml(
            f"""<html><body style="background:#1a1a1a; color:#e8e8e8; padding:30px; font-family:'맑은 고딕';">
            <h2 style="color:#FF6B35;">⚠ 정보지 생성 중 오류가 발생했습니다</h2>
            <p style="color:#aaa;">{message}</p>
            <p>API 키 설정을 확인하거나, 확인 버튼을 눌러 계속 진행하세요.</p>
            </body></html>"""
        )
        self.confirm_btn.setEnabled(True)
        self.refresh_btn.setEnabled(True)

    def _on_confirmed(self):
        """확인 버튼 클릭 → DB 기록 후 메인 창 시작"""
        mark_briefing_confirmed()
        self.confirmed.emit()
        self.accept()

    def _regenerate(self):
        """재생성 버튼"""
        self.refresh_btn.setEnabled(False)
        self.confirm_btn.setEnabled(False)
        self.content_browser.setVisible(False)
        self.loading_frame.setVisible(True)
        self.loading_label.setText("재생성 중...")

        # 캐시 무시하고 재생성
        self._thread = QThread()
        self._worker = BriefingLoader()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_loaded)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.start()

    def _update_countdown(self):
        """카운트다운 갱신"""
        now = datetime.now()
        market_open = now.replace(hour=9, minute=0, second=0)
        remaining = max(0, int((market_open - now).total_seconds()))
        if remaining > 0:
            h, m = divmod(remaining // 60, 60)
            time_str = f"장 개장까지 {h}시간 {m}분" if h > 0 else f"장 개장까지 {m}분"
        else:
            time_str = "🔴 장 운영 중"
        self.countdown_label.setText(time_str)

    def closeEvent(self, event):
        """X버튼으로 닫으면 확인한 것으로 처리"""
        if not is_briefing_confirmed_today():
            mark_briefing_confirmed()
            self.confirmed.emit()
        event.accept()
