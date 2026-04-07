"""
KIS API 인증 관리
AppKey/AppSecret → Access Token 발급 및 자동 갱신
토큰은 하루 유효하므로 만료 전 자동 재발급합니다.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

from config import (
    KIS_APP_KEY, KIS_APP_SECRET,
    KIS_BASE_URL, KIS_VIRTUAL_BASE_URL,
    KIS_WS_URL, KIS_VIRTUAL_WS_URL,
    KIS_IS_VIRTUAL, DATA_DIR,
)

logger = logging.getLogger(__name__)

TOKEN_CACHE_FILE = DATA_DIR / "kis_token.json"


class KISAuth:
    """
    KIS API 토큰 관리자
    - 최초 실행 시 토큰 발급
    - 만료 1시간 전 자동 갱신
    - 파일 캐시로 재시작 시 재발급 불필요
    """

    def __init__(self):
        self.app_key = KIS_APP_KEY
        self.app_secret = KIS_APP_SECRET
        self.is_virtual = KIS_IS_VIRTUAL
        self.base_url = KIS_VIRTUAL_BASE_URL if KIS_IS_VIRTUAL else KIS_BASE_URL
        self.ws_url = KIS_VIRTUAL_WS_URL if KIS_IS_VIRTUAL else KIS_WS_URL

        self._access_token: str = ""
        self._token_expires_at: datetime = datetime.min
        self._ws_approval_key: str = ""

        self._load_cached_token()

    # ─── 토큰 발급 ────────────────────────────────────────────────────────────

    def _issue_token(self) -> bool:
        """Access Token 발급"""
        url = f"{self.base_url}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecretkey": self.app_secret,
        }

        try:
            resp = requests.post(url, json=body, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            self._access_token = data["access_token"]
            # 만료 시각 (보통 86400초 = 24시간)
            expires_in = int(data.get("expires_in", 86400))
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in - 3600)

            self._save_token_cache()
            env_type = "모의투자" if self.is_virtual else "실전투자"
            logger.info(f"KIS 토큰 발급 완료 [{env_type}] 만료: {self._token_expires_at.strftime('%Y-%m-%d %H:%M')}")
            return True

        except requests.exceptions.HTTPError as e:
            logger.error(f"토큰 발급 HTTP 오류: {e.response.status_code} - {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"토큰 발급 오류: {e}")
            return False

    def _issue_ws_approval_key(self) -> bool:
        """WebSocket 접속키 발급"""
        url = f"{self.base_url}/oauth2/Approval"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "secretkey": self.app_secret,
        }

        try:
            resp = requests.post(url, json=body, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            self._ws_approval_key = data.get("approval_key", "")
            logger.info("KIS WebSocket 접속키 발급 완료")
            return bool(self._ws_approval_key)
        except Exception as e:
            logger.error(f"WebSocket 접속키 발급 오류: {e}")
            return False

    # ─── 캐시 관리 ────────────────────────────────────────────────────────────

    def _save_token_cache(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        cache = {
            "access_token": self._access_token,
            "expires_at": self._token_expires_at.isoformat(),
            "is_virtual": self.is_virtual,
        }
        TOKEN_CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")

    def _load_cached_token(self):
        if not TOKEN_CACHE_FILE.exists():
            return
        try:
            cache = json.loads(TOKEN_CACHE_FILE.read_text(encoding="utf-8"))
            # 환경(모의/실전)이 다르면 무시
            if cache.get("is_virtual") != self.is_virtual:
                return
            self._access_token = cache.get("access_token", "")
            self._token_expires_at = datetime.fromisoformat(cache["expires_at"])
            if self._access_token and self._token_expires_at > datetime.now():
                logger.info(f"캐시된 KIS 토큰 로드 (만료: {self._token_expires_at.strftime('%H:%M')})")
        except Exception:
            pass

    # ─── 퍼블릭 API ──────────────────────────────────────────────────────────

    def get_access_token(self) -> str:
        """유효한 Access Token 반환. 필요 시 자동 재발급."""
        if not self._access_token or datetime.now() >= self._token_expires_at:
            if not self._issue_token():
                raise RuntimeError("KIS Access Token 발급 실패. AppKey/AppSecret을 확인하세요.")
        return self._access_token

    def get_ws_approval_key(self) -> str:
        """WebSocket 접속키 반환. 필요 시 발급."""
        if not self._ws_approval_key:
            self._issue_ws_approval_key()
        return self._ws_approval_key

    def get_headers(self, tr_id: str, extra: dict = None) -> dict:
        """KIS REST API 공통 헤더 생성"""
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.get_access_token()}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",  # 개인
        }
        if extra:
            headers.update(extra)
        return headers

    def is_valid(self) -> bool:
        try:
            return bool(self.get_access_token())
        except Exception:
            return False


# 싱글턴
_auth_instance: KISAuth | None = None


def get_auth() -> KISAuth:
    global _auth_instance
    if _auth_instance is None:
        _auth_instance = KISAuth()
    return _auth_instance
