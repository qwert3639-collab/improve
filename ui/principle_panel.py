"""
투자 원칙 패널
추출된 투자 원칙을 좌측 패널에 표시하고, 채널 분석 기능을 제공합니다.
"""

import threading
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QProgressBar,
    QTextEdit, QGroupBox, QSplitter, QMessageBox,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QColor

from youtube.channel_crawler import crawl_channel, init_db
from youtube.transcript_fetcher import fetch_all_transcripts, get_unfetched_video_ids
from youtube.principle_extractor import (
    extract_principles_from_transcripts,
    load_principles_from_db,
    get_all_transcripts_from_db,
)
from config import DEFAULT_CHANNEL_URL


class AnalysisWorker(QObject):
    """채널 분석 작업을 백그라운드 스레드에서 실행"""
    progress = pyqtSignal(int, int, str)      # (current, total, message)
    finished = pyqtSignal(list)               # 완료 시 원칙 리스트
    error = pyqtSignal(str)                   # 오류 메시지

    def __init__(self, channel_url: str):
        super().__init__()
        self.channel_url = channel_url

    def run(self):
        try:
            # 1. 채널 크롤링
            self.progress.emit(0, 100, "채널 영상 목록 수집 중...")
            init_db()
            videos = crawl_channel(
                self.channel_url,
                lambda c, t, m: self.progress.emit(c, t or 1, m),
            )

            if not videos:
                self.error.emit("영상을 찾을 수 없습니다. URL을 확인하세요.")
                return

            total_videos = len(videos)
            self.progress.emit(0, total_videos, f"총 {total_videos}개 영상 발견. 자막 추출 중...")

            # 2. 자막 추출 (아직 가져오지 않은 것만)
            unfetched_ids = get_unfetched_video_ids()
            if unfetched_ids:
                fetch_all_transcripts(
                    unfetched_ids,
                    lambda c, t, m: self.progress.emit(c, t or 1, m),
                    delay=0.3,
                )

            # 3. 자막 데이터 로드
            transcripts = get_all_transcripts_from_db()
            if not transcripts:
                self.error.emit("추출된 자막이 없습니다. 한국어 자막이 없는 채널일 수 있습니다.")
                return

            self.progress.emit(0, 10, f"{len(transcripts)}개 자막으로 AI 원칙 분석 중...")

            # 4. Claude API 분석
            principles = extract_principles_from_transcripts(
                transcripts,
                channel_url=self.channel_url,
                progress_callback=lambda c, t, m: self.progress.emit(c, t or 1, m),
            )

            self.finished.emit(principles)

        except Exception as e:
            self.error.emit(f"분석 중 오류: {str(e)}")


class PrinciplePanel(QWidget):
    """투자 원칙 표시 + 채널 분석 UI 패널"""

    principles_updated = pyqtSignal(list)  # 원칙이 갱신될 때 상위로 전달

    def __init__(self, parent=None):
        super().__init__(parent)
        self.principles = []
        self._worker_thread: QThread | None = None
        self._setup_ui()
        self._try_load_existing_principles()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── 채널 URL 입력 그룹 ────────────────────────────────────────
        url_group = QGroupBox("유튜브 채널 분석")
        url_layout = QVBoxLayout(url_group)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.youtube.com/@채널명/videos")
        self.url_input.setText(DEFAULT_CHANNEL_URL)
        url_layout.addWidget(QLabel("채널 URL:"))
        url_layout.addWidget(self.url_input)

        btn_layout = QHBoxLayout()
        self.analyze_btn = QPushButton("채널 분석 시작")
        self.analyze_btn.setStyleSheet(
            "QPushButton { background: #1a73e8; color: white; padding: 6px; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background: #1557b0; }"
            "QPushButton:disabled { background: #cccccc; }"
        )
        self.analyze_btn.clicked.connect(self._start_analysis)

        self.reload_btn = QPushButton("원칙 다시 불러오기")
        self.reload_btn.clicked.connect(self._try_load_existing_principles)

        btn_layout.addWidget(self.analyze_btn)
        btn_layout.addWidget(self.reload_btn)
        url_layout.addLayout(btn_layout)

        # 진행바
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        url_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #555; font-size: 11px;")
        url_layout.addWidget(self.status_label)

        layout.addWidget(url_group)

        # ── 원칙 목록 ────────────────────────────────────────────────
        principles_group = QGroupBox("투자 원칙")
        principles_layout = QVBoxLayout(principles_group)

        self.principles_count = QLabel("원칙 0개")
        self.principles_count.setStyleSheet("font-weight: bold; color: #1a73e8;")
        principles_layout.addWidget(self.principles_count)

        self.principle_list = QListWidget()
        self.principle_list.setAlternatingRowColors(True)
        self.principle_list.itemClicked.connect(self._show_principle_detail)
        principles_layout.addWidget(self.principle_list)

        layout.addWidget(principles_group)

        # ── 원칙 상세 ────────────────────────────────────────────────
        detail_group = QGroupBox("선택한 원칙 상세")
        detail_layout = QVBoxLayout(detail_group)

        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMaximumHeight(150)
        self.detail_text.setStyleSheet("font-size: 12px;")
        detail_layout.addWidget(self.detail_text)

        layout.addWidget(detail_group)

    def _try_load_existing_principles(self):
        """기존에 분석된 원칙이 있으면 로드"""
        principles = load_principles_from_db()
        if principles:
            self._display_principles(principles)
            self.status_label.setText(f"저장된 원칙 {len(principles)}개 로드 완료")

    def _start_analysis(self):
        """채널 분석 시작"""
        channel_url = self.url_input.text().strip()
        if not channel_url:
            QMessageBox.warning(self, "입력 오류", "유튜브 채널 URL을 입력하세요.")
            return

        self.analyze_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("분석 시작 중...")

        # 백그라운드 스레드에서 실행
        self._worker_thread = QThread()
        self._worker = AnalysisWorker(channel_url)
        self._worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker.error.connect(self._worker_thread.quit)

        self._worker_thread.start()

    def _on_progress(self, current: int, total: int, message: str):
        if total > 0:
            pct = int(current / total * 100)
            self.progress_bar.setValue(pct)
        self.status_label.setText(message)

    def _on_finished(self, principles: list):
        self._display_principles(principles)
        self.progress_bar.setVisible(False)
        self.analyze_btn.setEnabled(True)
        self.status_label.setText(f"분석 완료! {len(principles)}개 원칙 추출됨")
        self.principles_updated.emit(principles)

    def _on_error(self, message: str):
        self.progress_bar.setVisible(False)
        self.analyze_btn.setEnabled(True)
        self.status_label.setText(f"오류: {message}")
        QMessageBox.critical(self, "분석 오류", message)

    def _display_principles(self, principles: list):
        """원칙 목록을 리스트위젯에 표시"""
        self.principles = principles
        self.principle_list.clear()
        self.principles_count.setText(f"원칙 {len(principles)}개")

        category_colors = {
            "종목선택": "#1a73e8",
            "매수시점": "#0f9d58",
            "매도시점": "#ea4335",
            "리스크관리": "#f4b400",
            "시장분석": "#9c27b0",
            "기타": "#757575",
        }

        for p in principles:
            category = p.get("category", "기타")
            title = p.get("title", "")
            item_text = f"[{category}] {title}"
            item = QListWidgetItem(item_text)

            color = category_colors.get(category, "#757575")
            item.setForeground(QColor(color))
            item.setData(Qt.UserRole, p)

            self.principle_list.addItem(item)

    def _show_principle_detail(self, item: QListWidgetItem):
        """선택한 원칙의 상세 정보 표시"""
        principle = item.data(Qt.UserRole)
        if not principle:
            return

        text = f"【{principle.get('title', '')}】\n\n"
        text += f"카테고리: {principle.get('category', '')}\n\n"
        text += f"설명: {principle.get('description', '')}\n\n"

        conditions = principle.get("conditions", [])
        if conditions:
            text += "조건:\n" + "\n".join(f"  • {c}" for c in conditions) + "\n\n"

        indicators = principle.get("indicators", [])
        if indicators:
            text += "지표: " + ", ".join(indicators) + "\n"

        self.detail_text.setPlainText(text)

    def get_principles(self) -> list:
        return self.principles
