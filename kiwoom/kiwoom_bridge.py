"""
키움 브릿지 (64비트 메인 프로세스용)
32비트 kiwoom_server.py와 소켓으로 통신하여 시세 데이터를 가져옵니다.
"""

import socket
import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from config import KIWOOM_HOST, KIWOOM_PORT, KIWOOM_TIMEOUT, TARGET_MARKET

logger = logging.getLogger(__name__)


class KiwoomBridge:
    """64비트 프로세스에서 키움 서버와 통신하는 클라이언트"""

    def __init__(self):
        self._server_process: Optional[subprocess.Popen] = None
        self._connected = False

    # ─── 서버 프로세스 관리 ────────────────────────────────────────────────────

    def start_server(self) -> bool:
        """
        32비트 키움 서버를 백그라운드 프로세스로 시작합니다.
        py -3.8-32 명령어로 kiwoom_server.py를 실행합니다.
        """
        server_script = Path(__file__).parent / "kiwoom_server.py"

        # 32비트 Python 찾기
        py32_cmds = ["py -3.8-32", "py -3.9-32", "py -3.10-32"]
        py32_cmd = None

        for cmd in py32_cmds:
            try:
                result = subprocess.run(
                    cmd.split() + ["--version"],
                    capture_output=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    py32_cmd = cmd.split()
                    break
            except Exception:
                continue

        if not py32_cmd:
            logger.error("32비트 Python을 찾을 수 없습니다.")
            logger.error("setup/install_32bit.bat 를 실행하여 32비트 Python을 설치하세요.")
            return False

        logger.info(f"키움 서버 시작 중: {' '.join(py32_cmd)} {server_script}")

        self._server_process = subprocess.Popen(
            py32_cmd + [str(server_script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 서버가 준비될 때까지 대기 (최대 30초)
        for i in range(30):
            time.sleep(1)
            if self.ping():
                logger.info("키움 서버 연결 성공")
                self._connected = True
                return True
            logger.debug(f"서버 대기 중... ({i+1}/30)")

        logger.error("키움 서버 시작 타임아웃")
        return False

    def stop_server(self):
        """키움 서버 프로세스 종료"""
        if self._server_process:
            self._server_process.terminate()
            self._server_process = None
        self._connected = False
        logger.info("키움 서버 종료")

    # ─── 소켓 통신 ──────────────────────────────────────────────────────────────

    def _send_request(self, request: dict) -> Optional[dict]:
        """소켓으로 요청을 보내고 응답을 받습니다."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(KIWOOM_TIMEOUT)
                s.connect((KIWOOM_HOST, KIWOOM_PORT))
                s.sendall(json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\n")

                data = b""
                while True:
                    chunk = s.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                    if data.endswith(b"\n"):
                        break

            return json.loads(data.decode("utf-8"))

        except ConnectionRefusedError:
            logger.error("키움 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요.")
            self._connected = False
            return None
        except socket.timeout:
            logger.error("키움 서버 응답 타임아웃")
            return None
        except Exception as e:
            logger.error(f"소켓 통신 오류: {e}")
            return None

    # ─── API 메서드 ────────────────────────────────────────────────────────────

    def ping(self) -> bool:
        """서버 연결 상태 확인"""
        response = self._send_request({"action": "ping"})
        return response is not None and response.get("status") == "ok"

    def is_connected(self) -> bool:
        return self._connected and self.ping()

    def get_stock_price(self, code: str) -> Optional[dict]:
        """단일 종목 현재가 조회"""
        response = self._send_request({"action": "get_price", "code": code})
        if response and response.get("status") == "ok":
            return response.get("data")
        return None

    def get_stock_list(self, market: str = "0") -> list[str]:
        """
        종목 코드 목록 조회
        market: "0"=KOSPI, "10"=KOSDAQ
        """
        response = self._send_request({"action": "get_stock_list", "market": market})
        if response and response.get("status") == "ok":
            return response.get("data", [])
        return []

    def get_market_data(self, max_stocks: int = 200) -> list[dict]:
        """
        KOSPI/KOSDAQ 전체 종목 현재가 데이터 조회
        추천 엔진에 사용할 스크리닝 데이터를 반환합니다.
        """
        if TARGET_MARKET == "KOSPI":
            markets = ["0"]
        elif TARGET_MARKET == "KOSDAQ":
            markets = ["10"]
        else:  # ALL
            markets = ["0", "10"]

        all_codes = []
        for market in markets:
            codes = self.get_stock_list(market)
            all_codes.extend(codes[:max_stocks // len(markets)])

        if not all_codes:
            return []

        response = self._send_request({
            "action": "get_prices",
            "codes": all_codes[:max_stocks],
        })
        if response and response.get("status") == "ok":
            return response.get("data", [])
        return []

    def get_realtime_candidates(self, codes: list[str]) -> list[dict]:
        """특정 종목 코드 리스트의 현재가를 조회합니다."""
        response = self._send_request({"action": "get_prices", "codes": codes})
        if response and response.get("status") == "ok":
            return response.get("data", [])
        return []


# 싱글턴 인스턴스
_bridge_instance: Optional[KiwoomBridge] = None


def get_bridge() -> KiwoomBridge:
    """KiwoomBridge 싱글턴 반환"""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = KiwoomBridge()
    return _bridge_instance
