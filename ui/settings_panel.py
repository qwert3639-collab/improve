"""
AI 및 API 설정 다이얼로그
Claude, OpenAI, Gemini, Ollama 중 원하는 AI를 선택하고
API 키를 입력하여 .env 파일에 저장합니다.
"""

from pathlib import Path
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QComboBox, QPushButton, QGroupBox,
    QFormLayout, QMessageBox, QCheckBox, QTextEdit, QSplitter,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from ai.providers import (
    PROVIDER_NAMES, CLAUDE_MODELS, OPENAI_MODELS, GEMINI_MODELS, OLLAMA_MODELS,
    get_ai_manager,
)

ENV_PATH = Path(__file__).parent.parent / ".env"


def _read_env() -> dict:
    """현재 .env 파일 내용을 딕셔너리로 읽기"""
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def _write_env(env: dict):
    """딕셔너리를 .env 파일로 저장"""
    lines = []
    for k, v in env.items():
        lines.append(f"{k}={v}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


class AISettingsTab(QWidget):
    """AI 프로바이더 설정 탭"""

    provider_changed = pyqtSignal(str, str, str)  # (provider_type, api_key, model)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._load_current_settings()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── 안내 문구 ──────────────────────────────────────────────
        info = QLabel(
            "사용할 AI를 선택하고 API 키를 입력하세요.\n"
            "Ollama(로컬)는 API 키 없이 무료로 사용 가능합니다."
        )
        info.setStyleSheet("color: #555; background: #f0f4ff; padding: 8px; border-radius: 4px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        # ── 분석용 AI ─────────────────────────────────────────────
        analysis_group = QGroupBox("채널 분석용 AI (투자 원칙 추출)")
        analysis_layout = QFormLayout(analysis_group)

        self.analysis_provider = QComboBox()
        for key, name in PROVIDER_NAMES.items():
            self.analysis_provider.addItem(name, key)
        self.analysis_provider.currentIndexChanged.connect(self._on_analysis_provider_changed)
        analysis_layout.addRow("AI 선택:", self.analysis_provider)

        self.analysis_model = QComboBox()
        self.analysis_model.setEditable(True)
        analysis_layout.addRow("모델:", self.analysis_model)

        self.analysis_key = QLineEdit()
        self.analysis_key.setPlaceholderText("API 키 입력 (Ollama는 불필요)")
        self.analysis_key.setEchoMode(QLineEdit.Password)
        analysis_layout.addRow("API 키:", self.analysis_key)

        self.analysis_show_key = QCheckBox("키 표시")
        self.analysis_show_key.toggled.connect(
            lambda checked: self.analysis_key.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )
        analysis_layout.addRow("", self.analysis_show_key)

        layout.addWidget(analysis_group)

        # ── 추천용 AI ─────────────────────────────────────────────
        rec_group = QGroupBox("종목 추천용 AI (빠른 분석, 비용 절약)")
        rec_layout = QFormLayout(rec_group)

        self.same_as_analysis = QCheckBox("채널 분석용과 동일하게 사용")
        self.same_as_analysis.setChecked(True)
        self.same_as_analysis.toggled.connect(self._on_same_toggled)
        rec_layout.addRow("", self.same_as_analysis)

        self.rec_provider = QComboBox()
        for key, name in PROVIDER_NAMES.items():
            self.rec_provider.addItem(name, key)
        self.rec_provider.setEnabled(False)
        self.rec_provider.currentIndexChanged.connect(self._on_rec_provider_changed)
        rec_layout.addRow("AI 선택:", self.rec_provider)

        self.rec_model = QComboBox()
        self.rec_model.setEditable(True)
        self.rec_model.setEnabled(False)
        rec_layout.addRow("모델:", self.rec_model)

        self.rec_key = QLineEdit()
        self.rec_key.setPlaceholderText("분석용과 다른 키 사용 시 입력")
        self.rec_key.setEchoMode(QLineEdit.Password)
        self.rec_key.setEnabled(False)
        rec_layout.addRow("API 키:", self.rec_key)

        layout.addWidget(rec_group)

        # ── Ollama 설정 ──────────────────────────────────────────
        self.ollama_group = QGroupBox("Ollama 설정 (로컬 AI 사용 시)")
        self.ollama_group.setVisible(False)
        ollama_layout = QFormLayout(self.ollama_group)

        self.ollama_url = QLineEdit("http://localhost:11434")
        ollama_layout.addRow("서버 URL:", self.ollama_url)

        ollama_info = QLabel(
            "Ollama 설치: https://ollama.com\n"
            "모델 다운로드 예시:\n"
            "  ollama pull llama3.2\n"
            "  ollama pull qwen2.5\n"
            "  ollama pull gemma2"
        )
        ollama_info.setStyleSheet("color: #666; font-size: 11px; font-family: monospace;")
        ollama_layout.addRow("", ollama_info)
        layout.addWidget(self.ollama_group)

        # ── 비용 안내 ──────────────────────────────────────────────
        cost_group = QGroupBox("AI 사용 비용 참고 (장 시간 전일 기준, 15분 주기 추천)")
        cost_layout = QVBoxLayout(cost_group)
        cost_text = QLabel(
            "• Claude Haiku   : 약 $4/월  ← 추천 (가성비 최고)\n"
            "• Claude Sonnet  : 약 $17/월\n"
            "• GPT-4o-mini    : 약 $3/월\n"
            "• Gemini Flash   : 약 $1/월 (무료 한도 있음)\n"
            "• Ollama (로컬)   : 무료 (PC 사양 필요)"
        )
        cost_text.setStyleSheet("font-family: monospace; font-size: 11px; color: #333;")
        cost_layout.addWidget(cost_text)
        layout.addWidget(cost_group)

        layout.addStretch()

    def _on_analysis_provider_changed(self, _):
        ptype = self.analysis_provider.currentData()
        self._update_model_list(self.analysis_model, ptype)
        self.ollama_group.setVisible(
            ptype == "ollama" or self.rec_provider.currentData() == "ollama"
        )
        self.analysis_key.setEnabled(ptype != "ollama")

    def _on_rec_provider_changed(self, _):
        ptype = self.rec_provider.currentData()
        self._update_model_list(self.rec_model, ptype)
        self.ollama_group.setVisible(
            ptype == "ollama" or self.analysis_provider.currentData() == "ollama"
        )
        self.rec_key.setEnabled(ptype != "ollama")

    def _on_same_toggled(self, checked: bool):
        self.rec_provider.setEnabled(not checked)
        self.rec_model.setEnabled(not checked)
        self.rec_key.setEnabled(not checked)

    def _update_model_list(self, combo: QComboBox, provider_type: str):
        combo.clear()
        models = {
            "claude": CLAUDE_MODELS,
            "openai": OPENAI_MODELS,
            "gemini": GEMINI_MODELS,
            "ollama": OLLAMA_MODELS,
        }.get(provider_type, [])
        combo.addItems(models)

    def _load_current_settings(self):
        """현재 설정 값 로드"""
        import config
        env = _read_env()

        provider = getattr(config, "AI_PROVIDER", "claude")
        idx = self.analysis_provider.findData(provider)
        if idx >= 0:
            self.analysis_provider.setCurrentIndex(idx)
        self._on_analysis_provider_changed(0)

        api_key = env.get("AI_API_KEY") or env.get("ANTHROPIC_API_KEY", "")
        if api_key and "여기에" not in api_key:
            self.analysis_key.setText(api_key)

        model = getattr(config, "AI_MODEL", "")
        if model:
            idx = self.analysis_model.findText(model)
            if idx >= 0:
                self.analysis_model.setCurrentIndex(idx)
            else:
                self.analysis_model.setCurrentText(model)

    def get_settings(self) -> dict:
        """현재 입력된 설정값 반환"""
        return {
            "analysis_provider": self.analysis_provider.currentData(),
            "analysis_model": self.analysis_model.currentText(),
            "analysis_key": self.analysis_key.text().strip(),
            "same_provider": self.same_as_analysis.isChecked(),
            "rec_provider": self.rec_provider.currentData() if not self.same_as_analysis.isChecked() else self.analysis_provider.currentData(),
            "rec_model": self.rec_model.currentText() if not self.same_as_analysis.isChecked() else self.analysis_model.currentText(),
            "rec_key": self.rec_key.text().strip() if not self.same_as_analysis.isChecked() else self.analysis_key.text().strip(),
            "ollama_url": self.ollama_url.text().strip(),
        }


class KISSettingsTab(QWidget):
    """한국투자증권 KIS API 설정 탭"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._load_current_settings()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 안내
        info = QLabel(
            "한국투자증권 KIS Developers에서 발급받은 키를 입력하세요.\n"
            "별도 소프트웨어 설치 없이 API 키만으로 사용 가능합니다."
        )
        info.setStyleSheet("color: #555; background: #f0fff4; padding: 8px; border-radius: 4px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        # KIS 설정 그룹
        kis_group = QGroupBox("KIS API 키")
        kis_layout = QFormLayout(kis_group)

        self.app_key = QLineEdit()
        self.app_key.setPlaceholderText("AppKey (PS로 시작하는 36자리)")
        kis_layout.addRow("AppKey:", self.app_key)

        self.app_secret = QLineEdit()
        self.app_secret.setPlaceholderText("AppSecret")
        self.app_secret.setEchoMode(QLineEdit.Password)
        kis_layout.addRow("AppSecret:", self.app_secret)

        show_secret = QCheckBox("Secret 표시")
        show_secret.toggled.connect(
            lambda c: self.app_secret.setEchoMode(QLineEdit.Normal if c else QLineEdit.Password)
        )
        kis_layout.addRow("", show_secret)

        self.is_virtual = QCheckBox("모의투자 모드 (처음에는 반드시 체크!)")
        self.is_virtual.setChecked(True)
        self.is_virtual.setStyleSheet("color: #d32f2f; font-weight: bold;")
        kis_layout.addRow("", self.is_virtual)

        layout.addWidget(kis_group)

        # 발급 안내
        guide_group = QGroupBox("KIS API 키 발급 방법")
        guide_layout = QVBoxLayout(guide_group)
        guide_text = QLabel(
            "1. 한국투자증권 계좌 개설 (앱 또는 영업점)\n"
            "2. https://apiportal.koreainvestment.com 접속\n"
            "3. 로그인 → 앱 관리 → 앱 추가\n"
            "4. AppKey / AppSecret 복사 후 위에 입력\n\n"
            "※ 모의투자 키와 실전투자 키는 별도로 발급받습니다"
        )
        guide_text.setStyleSheet("font-size: 12px; color: #444;")
        guide_layout.addWidget(guide_text)
        layout.addWidget(guide_group)

        layout.addStretch()

    def _load_current_settings(self):
        import config
        env = _read_env()

        app_key = env.get("KIS_APP_KEY", getattr(config, "KIS_APP_KEY", ""))
        app_secret = env.get("KIS_APP_SECRET", getattr(config, "KIS_APP_SECRET", ""))

        if app_key and "여기에" not in app_key:
            self.app_key.setText(app_key)
        if app_secret and "여기에" not in app_secret:
            self.app_secret.setText(app_secret)

        self.is_virtual.setChecked(getattr(config, "KIS_IS_VIRTUAL", True))

    def get_settings(self) -> dict:
        return {
            "KIS_APP_KEY": self.app_key.text().strip(),
            "KIS_APP_SECRET": self.app_secret.text().strip(),
            "KIS_IS_VIRTUAL": "true" if self.is_virtual.isChecked() else "false",
        }


class SettingsDialog(QDialog):
    """전체 설정 다이얼로그 (AI + KIS API)"""

    settings_saved = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("API 설정")
        self.setMinimumSize(600, 580)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 탭
        tabs = QTabWidget()
        self.ai_tab = AISettingsTab()
        self.kis_tab = KISSettingsTab()
        tabs.addTab(self.ai_tab, "AI 설정")
        tabs.addTab(self.kis_tab, "KIS API (시세)")
        layout.addWidget(tabs)

        # 저장/취소 버튼
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("저장 및 적용")
        save_btn.setStyleSheet(
            "QPushButton { background: #1a73e8; color: white; padding: 8px 20px; "
            "border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background: #1557b0; }"
        )
        save_btn.clicked.connect(self._save)

        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def _save(self):
        """설정 저장 및 런타임 적용"""
        import config

        ai_settings = self.ai_tab.get_settings()
        kis_settings = self.kis_tab.get_settings()

        # 유효성 검사
        analysis_provider = ai_settings["analysis_provider"]
        analysis_key = ai_settings["analysis_key"]

        if analysis_provider != "ollama" and not analysis_key:
            QMessageBox.warning(self, "입력 오류", "AI API 키를 입력해주세요.")
            return

        kis_key = kis_settings["KIS_APP_KEY"]
        kis_secret = kis_settings["KIS_APP_SECRET"]
        if not kis_key or not kis_secret:
            reply = QMessageBox.question(
                self, "KIS 키 미입력",
                "KIS API 키가 입력되지 않았습니다.\n시세 조회 기능이 작동하지 않습니다.\n그래도 저장하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.No:
                return

        # .env 파일 업데이트
        env = _read_env()
        env["AI_PROVIDER"] = analysis_provider
        env["AI_MODEL"] = ai_settings["analysis_model"]

        if analysis_key:
            env["AI_API_KEY"] = analysis_key
            # Claude인 경우 기존 ANTHROPIC_API_KEY도 업데이트
            if analysis_provider == "claude":
                env["ANTHROPIC_API_KEY"] = analysis_key

        if ai_settings["ollama_url"] != "http://localhost:11434":
            env["OLLAMA_BASE_URL"] = ai_settings["ollama_url"]

        if kis_key:
            env["KIS_APP_KEY"] = kis_key
        if kis_secret:
            env["KIS_APP_SECRET"] = kis_secret
        env["KIS_IS_VIRTUAL"] = kis_settings["KIS_IS_VIRTUAL"]

        _write_env(env)

        # 런타임 config 업데이트
        config.AI_PROVIDER = analysis_provider
        config.AI_MODEL = ai_settings["analysis_model"]
        if analysis_key:
            config.AI_API_KEY = analysis_key
            if analysis_provider == "claude":
                config.ANTHROPIC_API_KEY = analysis_key
        if kis_key:
            config.KIS_APP_KEY = kis_key
        if kis_secret:
            config.KIS_APP_SECRET = kis_secret
        config.KIS_IS_VIRTUAL = (kis_settings["KIS_IS_VIRTUAL"] == "true")

        # AI 매니저 재초기화
        import ai.providers as ai_module
        ai_module._manager = None
        manager = get_ai_manager()
        try:
            manager.set_provider(
                analysis_provider,
                analysis_key,
                ai_settings["analysis_model"],
                ai_settings["ollama_url"],
                use_for="analysis",
            )
            if not ai_settings["same_provider"]:
                manager.set_provider(
                    ai_settings["rec_provider"],
                    ai_settings["rec_key"],
                    ai_settings["rec_model"],
                    ai_settings["ollama_url"],
                    use_for="recommend",
                )
        except Exception as e:
            QMessageBox.critical(self, "설정 오류", str(e))
            return

        # KIS auth 재초기화
        import kis.kis_auth as kis_auth_module
        import kis.kis_client as kis_client_module
        kis_auth_module._auth_instance = None
        kis_client_module._client_instance = None

        QMessageBox.information(self, "저장 완료", "설정이 저장되었습니다.")
        self.settings_saved.emit()
        self.accept()
