"""
투자 원칙 기반 분석 보고서 다이얼로그
AI가 종목을 분석할 때마다 팝업으로 표시.
어떤 원칙이 적용됐고 왜 추천하는지를 요약 보고서 형태로 보여줌.
확인 버튼으로 닫기.
"""

from datetime import datetime
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextBrowser, QFrame, QScrollArea, QWidget, QGridLayout,
    QSplitter, QTabWidget,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor


def _make_score_bar(score: int) -> str:
    """점수를 HTML 프로그레스 바로 변환"""
    filled = int(score / 10)
    color = "#0f9d58" if score >= 70 else "#f4b400" if score >= 40 else "#ea4335"
    bar = "█" * filled + "░" * (10 - filled)
    return f'<span style="color:{color}; font-family:monospace;">{bar}</span> <b style="color:{color};">{score}점</b>'


def _action_badge(action: str) -> str:
    """액션 배지 HTML"""
    configs = {
        "BUY": ("매수 검토", "#0f9d58", "#e8f5e9"),
        "WATCH": ("관찰", "#f57c00", "#fff8e1"),
        "SKIP": ("제외", "#9e9e9e", "#f5f5f5"),
    }
    label, fg, bg = configs.get(action, ("분석중", "#555", "#eee"))
    return (
        f'<span style="background:{bg}; color:{fg}; border:1px solid {fg}; '
        f'border-radius:4px; padding:2px 8px; font-weight:bold; font-size:12px;">'
        f'{label}</span>'
    )


def build_report_html(
    recommendations: list[dict],
    principles: list[dict],
    generated_at: datetime = None,
) -> str:
    """추천 결과를 HTML 보고서로 변환"""

    if generated_at is None:
        generated_at = datetime.now()

    principles_map = {p["id"]: p for p in principles}
    time_str = generated_at.strftime("%Y.%m.%d %H:%M:%S")
    count = len(recommendations)

    buy_count = sum(1 for r in recommendations if r.get("action") == "BUY")
    watch_count = sum(1 for r in recommendations if r.get("action") == "WATCH")

    # 적용된 원칙 집계
    all_matched = {}
    for rec in recommendations:
        for pid in rec.get("matched_principles", []):
            all_matched[pid] = all_matched.get(pid, 0) + 1

    top_principles_html = ""
    if all_matched:
        sorted_principles = sorted(all_matched.items(), key=lambda x: x[1], reverse=True)
        for pid, cnt in sorted_principles[:5]:
            p = principles_map.get(pid, {})
            title = p.get("title", pid)
            category = p.get("category", "")
            top_principles_html += (
                f'<li><b>[{category}]</b> {title} '
                f'<span style="color:#1a73e8;">({cnt}개 종목 해당)</span></li>'
            )

    # 종목별 섹션
    stocks_html = ""
    for rec in recommendations:
        code = rec.get("code", "")
        name = rec.get("name", "")
        price = rec.get("price", 0)
        change = rec.get("change_rate", 0)
        change_color = "#d32f2f" if change >= 0 else "#1565c0"
        change_str = f"{change:+.2f}%"
        score = rec.get("score", 0)
        action = rec.get("action", "WATCH")
        reason = rec.get("reason", "")
        caution = rec.get("caution", "")
        matched_ids = rec.get("matched_principles", [])
        principle_titles = rec.get("principle_titles", [])

        # 매칭된 원칙 태그
        tags_html = ""
        for i, pid in enumerate(matched_ids[:4]):
            title = principle_titles[i] if i < len(principle_titles) else pid
            tags_html += (
                f'<span style="background:#e8f0fe; color:#1a73e8; border-radius:3px; '
                f'padding:1px 6px; margin:2px; font-size:11px; display:inline-block;">'
                f'{title}</span> '
            )

        caution_html = ""
        if caution and caution not in ("AI 분석 대기 중", ""):
            caution_html = (
                f'<p style="color:#e53935; background:#fff3f3; border-left:3px solid #e53935; '
                f'padding:6px 10px; margin:6px 0;">⚠ {caution}</p>'
            )

        stocks_html += f"""
<div style="border:1px solid #e0e0e0; border-radius:8px; margin:10px 0; padding:14px;
            background: {'#f8fff8' if action=='BUY' else '#fffdf8' if action=='WATCH' else '#fafafa'};">
  <div style="display:flex; align-items:center; margin-bottom:8px;">
    <span style="font-size:16px; font-weight:bold; color:#333;">{name}</span>
    <span style="color:#888; margin:0 8px; font-size:13px;">({code})</span>
    {_action_badge(action)}
    <span style="margin-left:auto; font-size:16px; font-weight:bold;">{price:,}원</span>
    <span style="color:{change_color}; margin-left:8px; font-weight:bold;">{change_str}</span>
  </div>
  <div style="margin-bottom:6px;">{_make_score_bar(score)}</div>
  <div style="margin:6px 0;">{tags_html}</div>
  <p style="color:#444; margin:8px 0; line-height:1.6; font-size:13px;">{reason}</p>
  {caution_html}
</div>"""

    # 전체 HTML
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: '맑은 고딕', Arial, sans-serif; margin: 0; padding: 16px; color: #333; background: #fff; }}
  h1 {{ color: #1a73e8; font-size: 18px; border-bottom: 2px solid #1a73e8; padding-bottom: 8px; }}
  h2 {{ color: #444; font-size: 15px; margin-top: 20px; border-left: 4px solid #1a73e8; padding-left: 10px; }}
  .summary-box {{ background: #f0f4ff; border-radius: 8px; padding: 14px; margin: 12px 0; }}
  .stat {{ display: inline-block; margin-right: 20px; }}
  .stat .num {{ font-size: 28px; font-weight: bold; color: #1a73e8; }}
  .stat .label {{ font-size: 12px; color: #888; }}
  ul {{ line-height: 2; padding-left: 20px; }}
</style>
</head>
<body>

<h1>📊 투자 원칙 기반 분석 보고서</h1>
<p style="color:#888; font-size:12px;">생성 시각: {time_str} | AI 분석 결과 (15분 주기)</p>

<div class="summary-box">
  <div class="stat">
    <div class="num">{count}</div>
    <div class="label">분석 종목</div>
  </div>
  <div class="stat">
    <div class="num" style="color:#0f9d58;">{buy_count}</div>
    <div class="label">매수 검토</div>
  </div>
  <div class="stat">
    <div class="num" style="color:#f57c00;">{watch_count}</div>
    <div class="label">관찰</div>
  </div>
</div>

<h2>이번 분석에 적용된 투자 원칙</h2>
<ul>{top_principles_html if top_principles_html else '<li>원칙이 아직 로드되지 않았습니다.</li>'}</ul>

<h2>종목별 분석 결과</h2>
{stocks_html if stocks_html else '<p style="color:#888;">분석된 종목이 없습니다.</p>'}

<hr style="border:none; border-top:1px solid #eee; margin-top:20px;">
<p style="color:#bbb; font-size:11px; text-align:center;">
  이 보고서는 AI가 투자 원칙을 적용하여 생성한 참고 자료입니다.<br>
  매매는 직접 HTS/MTS에서 실행하세요.
</p>

</body>
</html>"""


class AnalysisReportDialog(QDialog):
    """
    분석 보고서 팝업 다이얼로그.
    AI 분석 완료 시 자동으로 팝업.
    확인 버튼으로 닫기.
    """

    def __init__(self, recommendations: list[dict], principles: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("투자 원칙 기반 분석 보고서")
        self.setMinimumSize(800, 620)
        self.resize(860, 680)
        self._setup_ui(recommendations, principles)

    def _setup_ui(self, recommendations: list[dict], principles: list[dict]):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 본문 (HTML 보고서)
        self.browser = QTextBrowser()
        self.browser.setStyleSheet("""
            QTextBrowser {
                border: none;
                background: white;
            }
        """)
        html = build_report_html(recommendations, principles)
        self.browser.setHtml(html)
        layout.addWidget(self.browser, 1)

        # 하단 버튼
        footer = QFrame()
        footer.setStyleSheet("background: #f5f5f5; border-top: 1px solid #ddd;")
        footer.setFixedHeight(54)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(16, 0, 16, 0)

        info_label = QLabel("⏱ 다음 분석은 15분 후")
        info_label.setStyleSheet("color: #888; font-size: 12px;")

        confirm_btn = QPushButton("✓  확인")
        confirm_btn.setFixedWidth(100)
        confirm_btn.setFont(QFont("맑은 고딕", 11, QFont.Bold))
        confirm_btn.setStyleSheet("""
            QPushButton {
                background: #1a73e8;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
            }
            QPushButton:hover { background: #1557b0; }
        """)
        confirm_btn.clicked.connect(self.accept)
        confirm_btn.setDefault(True)

        footer_layout.addWidget(info_label)
        footer_layout.addStretch()
        footer_layout.addWidget(confirm_btn)
        layout.addWidget(footer)


def show_analysis_report(
    recommendations: list[dict],
    principles: list[dict],
    parent=None,
    auto_close_seconds: int = 0,
) -> None:
    """
    분석 보고서를 팝업으로 표시하는 헬퍼 함수.

    Args:
        recommendations: 추천 종목 리스트
        principles: 투자 원칙 리스트
        parent: 부모 위젯
        auto_close_seconds: 0이면 수동 닫기, n이면 n초 후 자동 닫기
    """
    dialog = AnalysisReportDialog(recommendations, principles, parent)

    if auto_close_seconds > 0:
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(auto_close_seconds * 1000, dialog.accept)

    dialog.exec_()
