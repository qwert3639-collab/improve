"""
AI 프로바이더 추상화 레이어
Claude, OpenAI GPT, Google Gemini, Ollama(로컬) 등 어떤 AI든
동일한 인터페이스로 사용할 수 있습니다.

설정 위치: config.py 또는 UI의 AI 설정 패널
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Optional

import requests

logger = logging.getLogger(__name__)


# ─── 추상 기반 클래스 ──────────────────────────────────────────────────────────

class AIProvider(ABC):
    """모든 AI 프로바이더가 구현해야 하는 인터페이스"""

    @abstractmethod
    def chat(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
        """AI에 메시지를 보내고 응답 텍스트를 반환합니다."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """API 키가 설정되어 있고 사용 가능한지 확인"""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """프로바이더 이름"""
        ...


# ─── Claude (Anthropic) ────────────────────────────────────────────────────────

class ClaudeProvider(AIProvider):
    """Anthropic Claude API"""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        self.api_key = api_key
        self.model = model

    @property
    def name(self) -> str:
        return f"Claude ({self.model})"

    def is_available(self) -> bool:
        return bool(self.api_key) and "여기에" not in self.api_key

    def chat(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
        if not self.is_available():
            raise RuntimeError("Claude API 키가 설정되지 않았습니다.")
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)
            message = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return message.content[0].text
        except ImportError:
            raise RuntimeError("anthropic 패키지가 설치되지 않았습니다. pip install anthropic")


# ─── OpenAI GPT ───────────────────────────────────────────────────────────────

class OpenAIProvider(AIProvider):
    """OpenAI GPT API (GPT-4o, GPT-4o-mini 등)"""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model

    @property
    def name(self) -> str:
        return f"OpenAI ({self.model})"

    def is_available(self) -> bool:
        return bool(self.api_key) and "여기에" not in self.api_key

    def chat(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
        if not self.is_available():
            raise RuntimeError("OpenAI API 키가 설정되지 않았습니다.")
        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return response.choices[0].message.content
        except ImportError:
            raise RuntimeError("openai 패키지가 설치되지 않았습니다. pip install openai")


# ─── Google Gemini ────────────────────────────────────────────────────────────

class GeminiProvider(AIProvider):
    """Google Gemini API"""

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash"):
        self.api_key = api_key
        self.model = model

    @property
    def name(self) -> str:
        return f"Gemini ({self.model})"

    def is_available(self) -> bool:
        return bool(self.api_key) and "여기에" not in self.api_key

    def chat(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
        if not self.is_available():
            raise RuntimeError("Gemini API 키가 설정되지 않았습니다.")
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(
                self.model,
                system_instruction=system_prompt,
            )
            response = model.generate_content(
                user_prompt,
                generation_config={"max_output_tokens": max_tokens},
            )
            return response.text
        except ImportError:
            raise RuntimeError(
                "google-generativeai 패키지가 설치되지 않았습니다.\n"
                "pip install google-generativeai"
            )


# ─── Ollama (로컬 LLM) ────────────────────────────────────────────────────────

class OllamaProvider(AIProvider):
    """
    Ollama 로컬 LLM (API 키 불필요)
    ollama.com 에서 Ollama 설치 후 모델 다운로드 필요
    예: ollama pull llama3.2, ollama pull qwen2.5
    """

    def __init__(self, model: str = "llama3.2", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    @property
    def name(self) -> str:
        return f"Ollama/{self.model} (로컬)"

    def is_available(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def chat(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                "Ollama 서버에 연결할 수 없습니다.\n"
                "Ollama가 실행 중인지 확인하세요: ollama serve"
            )


# ─── 프로바이더 관리자 ────────────────────────────────────────────────────────

PROVIDER_NAMES = {
    "claude": "Claude (Anthropic)",
    "openai": "OpenAI GPT",
    "gemini": "Google Gemini",
    "ollama": "Ollama (로컬, 무료)",
}

CLAUDE_MODELS = [
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
    "claude-opus-4-6",
]

OPENAI_MODELS = [
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4-turbo",
]

GEMINI_MODELS = [
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash",
]

OLLAMA_MODELS = [
    "llama3.2",
    "qwen2.5",
    "mistral",
    "gemma2",
    "phi3",
]


class AIManager:
    """
    현재 활성 AI 프로바이더를 관리합니다.
    채널 분석용(analysis)과 종목 추천용(recommendation) 프로바이더를 분리할 수 있습니다.
    """

    def __init__(self):
        self._analysis_provider: Optional[AIProvider] = None    # 채널 분석 (고품질)
        self._recommend_provider: Optional[AIProvider] = None   # 종목 추천 (속도 중시)

    def set_provider(
        self,
        provider_type: str,
        api_key: str = "",
        model: str = "",
        base_url: str = "http://localhost:11434",
        use_for: str = "both",  # "both" | "analysis" | "recommend"
    ):
        """
        AI 프로바이더 설정

        Args:
            provider_type: "claude" | "openai" | "gemini" | "ollama"
            api_key: API 키
            model: 모델명 (비워두면 기본값)
            base_url: Ollama 서버 URL
            use_for: "both"=전체, "analysis"=채널분석만, "recommend"=종목추천만
        """
        provider = self._create_provider(provider_type, api_key, model, base_url)
        if use_for in ("both", "analysis"):
            self._analysis_provider = provider
        if use_for in ("both", "recommend"):
            self._recommend_provider = provider
        logger.info(f"AI 프로바이더 설정: {provider.name} (용도: {use_for})")

    def _create_provider(
        self, provider_type: str, api_key: str, model: str, base_url: str
    ) -> AIProvider:
        defaults = {
            "claude": "claude-haiku-4-5-20251001",  # 비용 절약
            "openai": "gpt-4o-mini",
            "gemini": "gemini-1.5-flash",
            "ollama": "llama3.2",
        }
        model = model or defaults.get(provider_type, "")

        if provider_type == "claude":
            return ClaudeProvider(api_key, model)
        elif provider_type == "openai":
            return OpenAIProvider(api_key, model)
        elif provider_type == "gemini":
            return GeminiProvider(api_key, model)
        elif provider_type == "ollama":
            return OllamaProvider(model, base_url)
        else:
            raise ValueError(f"알 수 없는 프로바이더: {provider_type}")

    def get_analysis_provider(self) -> Optional[AIProvider]:
        return self._analysis_provider

    def get_recommend_provider(self) -> Optional[AIProvider]:
        return self._recommend_provider or self._analysis_provider

    def chat_analysis(self, system: str, user: str, max_tokens: int = 4096) -> str:
        """채널 분석용 AI 호출"""
        p = self.get_analysis_provider()
        if not p:
            raise RuntimeError("AI 프로바이더가 설정되지 않았습니다.")
        return p.chat(system, user, max_tokens)

    def chat_recommend(self, system: str, user: str, max_tokens: int = 2048) -> str:
        """종목 추천용 AI 호출 (빠른 응답 우선)"""
        p = self.get_recommend_provider()
        if not p:
            raise RuntimeError("AI 프로바이더가 설정되지 않았습니다.")
        return p.chat(system, user, max_tokens)

    def is_ready(self) -> bool:
        p = self.get_analysis_provider()
        return p is not None and p.is_available()

    def get_status(self) -> str:
        analysis = self.get_analysis_provider()
        recommend = self.get_recommend_provider()
        if not analysis:
            return "AI 미설정"
        if analysis is recommend or recommend is None:
            return f"AI: {analysis.name}"
        return f"분석: {analysis.name} / 추천: {recommend.name}"


# 싱글턴
_manager: Optional[AIManager] = None


def get_ai_manager() -> AIManager:
    global _manager
    if _manager is None:
        _manager = AIManager()
        _load_default_provider()
    return _manager


def _load_default_provider():
    """config.py 설정 기반으로 기본 프로바이더 자동 로드"""
    import config
    manager = get_ai_manager()

    provider_type = getattr(config, "AI_PROVIDER", "claude")
    api_key = getattr(config, "AI_API_KEY", "") or getattr(config, "ANTHROPIC_API_KEY", "")
    model = getattr(config, "AI_MODEL", "")
    base_url = getattr(config, "OLLAMA_BASE_URL", "http://localhost:11434")

    if api_key and "여기에" not in api_key:
        try:
            manager.set_provider(provider_type, api_key, model, base_url)
        except Exception as e:
            logger.warning(f"기본 AI 프로바이더 로드 실패: {e}")
