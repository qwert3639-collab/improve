"""
실시간 종목 추천 패널
추천 종목 테이블, 상세 이유 팝업, 실시간 갱신 표시를 담당합니다.
"""

from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QDialog, QTextEdit, QGroupBox, QFrame,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QBrush


class RecommendationDetailDialog(QDialog):
    """종목 추천 이유 상세 팝업"""

    def __init__(self, rec: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"추천 이유: {rec.get('name', '')} ({rec.get('code', '')})")
        self.setMinimumSize(500, 400)
        self._setup_ui(rec)

    def _setup_ui(self, rec: dict):
        layout = QVBoxLayout(self)

        # 종목 기본 정보
        info_frame = QFrame()
        info_frame.setStyleSheet(
            "QFrame { background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px; padding: 10px; }"
        )
        info_layout = QHBoxLayout(info_frame)

        name_label = QLabel(f"{rec.get('name', '')} ({rec.get('code', '')})")
        name_label.setFont(QFont("", 14, QFont.Bold))

        price = rec.get("price", 0)
        change = rec.get("change_rate", 0)
        change_str = f"+{change:.2f}%" if change >= 0 else f"{change:.2f}%"
        change_color = "#e53935" if change >= 0 else "#1565c0"
        price_label = QLabel(f"{price:,}원  {change_str}")
        price_label.setStyleSheet(f"color: {change_color}; font-size: 14px; font-weight: bold;")

        score = rec.get("score", 0)
        action = rec.get("action", "WATCH")
        action_colors = {"BUY": "#0f9d58", "WATCH": "#f57c00", "SKIP": "#757575"}
        score_label = QLabel(f"★ {score}점  [{action}]")
        score_label.setStyleSheet(f"color: {action_colors.get(action, '#000')}; font-weight: bold; font-size: 13px;")

        info_layout.addWidget(name_label)
        info_layout.addStretch()
        info_layout.addWidget(price_label)
        info_layout.addWidget(score_label)
        layout.addWidget(info_frame)

        # 매칭된 원칙
        principle_titles = rec.get("principle_titles", [])
        matched = rec.get("matched_principles", [])
        if principle_titles or matched:
            p_group = QGroupBox("매칭된 투자 원칙")
            p_layout = QVBoxLayout(p_group)
            principles_text = "\n".join(
                f"  ✓ {t}" for t in (principle_titles or matched)
            )
            p_label = QLabel(principles_text)
            p_label.setWordWrap(True)
            p_layout.addWidget(p_label)
            layout.addWidget(p_group)

        # 추천 이유
        reason_group = QGroupBox("추천 이유")
        reason_layout = QVBoxLayout(reason_group)
        reason_text = QTextEdit()
        reason_text.setReadOnly(True)
        reason_text.setPlainText(rec.get("reason", "분석 중..."))
        reason_layout.addWidget(reason_text)
        layout.addWidget(reason_group)

        # 주의사항
        caution = rec.get("caution", "")
        if caution and caution != "AI 분석 대기 중":
            caution_group = QGroupBox("⚠ 주의사항")
            caution_layout = QVBoxLayout(caution_group)
            c_label = QLabel(caution)
            c_label.setWordWrap(True)
            c_label.setStyleSheet("color: #e53935;")
            caution_layout.addWidget(c_label)
            layout.addWidget(caution_group)

        # 닫기 버튼
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)


class RecommendationPanel(QWidget):
    """실시간 종목 추천 테이블 패널"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._recommendations = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # ── 상태 바 ──────────────────────────────────────────────────
        status_layout = QHBoxLayout()

        self.status_label = QLabel("키움 API 연결 대기 중...")
        self.status_label.setStyleSheet("color: #757575; font-size: 12px;")

        self.update_time_label = QLabel("")
        self.update_time_label.setStyleSheet("color: #555; font-size: 11px;")

        self.refresh_btn = QPushButton("수동 갱신")
        self.refresh_btn.setFixedWidth(80)

        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.update_time_label)
        status_layout.addWidget(self.refresh_btn)
        layout.addLayout(status_layout)

        # ── 추천 테이블 ───────────────────────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "종목명", "종목코드", "현재가", "등락률", "거래량", "점수", "추천"
        ])

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)   # 종목명
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)

        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setFont(QFont("", 11))
        self.table.doubleClicked.connect(self._show_detail)

        layout.addWidget(self.table)

        # ── 안내 문구 ────────────────────────────────────────────────
        hint = QLabel("* 종목을 더블클릭하면 추천 이유 상세 보기\n"
                       "* 매매는 직접 HTS/MTS에서 실행하세요")
        hint.setStyleSheet("color: #999; font-size: 10px;")
        layout.addWidget(hint)

    def update_recommendations(self, recommendations: list[dict]):
        """추천 종목 목록을 테이블에 갱신합니다."""
        self._recommendations = recommendations
        self.table.setRowCount(len(recommendations))

        action_colors = {
            "BUY": QColor("#e8f5e9"),
            "WATCH": QColor("#fff8e1"),
            "SKIP": QColor("#fafafa"),
        }

        for row, rec in enumerate(recommendations):
            action = rec.get("action", "WATCH")
            row_color = action_colors.get(action, QColor("white"))

            name_item = QTableWidgetItem(rec.get("name", ""))
            name_item.setData(Qt.UserRole, rec)

            code_item = QTableWidgetItem(rec.get("code", ""))

            price = rec.get("price", 0)
            price_item = QTableWidgetItem(f"{price:,}")
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            change = rec.get("change_rate", 0)
            change_str = f"+{change:.2f}%" if change >= 0 else f"{change:.2f}%"
            change_item = QTableWidgetItem(change_str)
            change_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if change >= 0:
                change_item.setForeground(QBrush(QColor("#e53935")))
            else:
                change_item.setForeground(QBrush(QColor("#1565c0")))

            volume = rec.get("volume", 0)
            volume_item = QTableWidgetItem(f"{volume:,}")
            volume_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            score = rec.get("score", 0)
            score_item = QTableWidgetItem(f"★ {score}")
            score_item.setTextAlignment(Qt.AlignCenter)

            action_texts = {"BUY": "매수검토", "WATCH": "관찰", "SKIP": "제외"}
            action_item = QTableWidgetItem(action_texts.get(action, action))
            action_item.setTextAlignment(Qt.AlignCenter)
            if action == "BUY":
                action_item.setForeground(QBrush(QColor("#0f9d58")))
                action_item.setFont(QFont("", 10, QFont.Bold))

            items = [name_item, code_item, price_item, change_item, volume_item, score_item, action_item]
            for col, item in enumerate(items):
                item.setBackground(QBrush(row_color))
                self.table.setItem(row, col, item)

        # 갱신 시각
        self.update_time_label.setText(f"갱신: {datetime.now().strftime('%H:%M:%S')}")
        self.status_label.setText(f"추천 종목 {len(recommendations)}개")

    def set_status(self, message: str, is_error: bool = False):
        color = "#e53935" if is_error else "#757575"
        self.status_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        self.status_label.setText(message)

    def _show_detail(self):
        """더블클릭 시 추천 이유 상세 팝업"""
        selected = self.table.selectedItems()
        if not selected:
            return

        row = self.table.currentRow()
        name_item = self.table.item(row, 0)
        if not name_item:
            return

        rec = name_item.data(Qt.UserRole)
        if rec:
            dialog = RecommendationDetailDialog(rec, self)
            dialog.exec_()
