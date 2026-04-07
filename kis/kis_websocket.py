"""
KIS WebSocket 실시간 시세
HTS 없이 실시간 체결가/호가를 수신합니다.
TR: H0STCNT0 (주식 체결)
"""

import asyncio
import json
import logging
import threading
import time
from typing import Callable, Optional

import websockets

from config import KIS_IS_VIRTUAL, KIS_WS_URL, KIS_VIRTUAL_WS_URL
from kis.kis_auth import get_auth

logger = logging.getLogger(__name__)

# 실시간 FID 매핑 (H0STCNT0 체결 데이터)
REALTIME_FIELDS = [
    "유가증권단축종목코드",   # 0: 종목코드
    "주식체결시간",           # 1: 체결시간
    "주식현재가",             # 2: 현재가
    "전일대비부호",           # 3: 부호
    "전일대비",               # 4: 전일대비
    "전일대비율",             # 5: 등락률
    "가중평균주식가격",        # 6: 가중평균가
    "주식시가",               # 7: 시가
    "주식최고가",             # 8: 고가
    "주식최저가",             # 9: 저가
    "매도호가1",              # 10: 매도호가
    "매수호가1",              # 11: 매수호가
    "체결거래량",             # 12: 체결거래량
    "누적거래량",             # 13: 누적거래량
    "누적거래대금",           # 14: 누적거래대금
]


def _parse_realtime(raw: str) -> Optional[dict]:
    """실시간 수신 데이터 파싱"""
    try:
        parts = raw.split("|")
        if len(parts) < 4:
            return None

        # parts[0]=암호화여부, parts[1]=TR_ID, parts[2]=데이터건수, parts[3]=데이터
        tr_id = parts[1]
        if tr_id != "H0STCNT0":
            return None

        fields = parts[3].split("^")
        if len(fields) < 14:
            return None

        code = fields[0]
        price = abs(int(fields[2])) if fields[2] else 0
        change_rate = float(fields[5]) if fields[5] else 0.0
        volume = int(fields[13]) if fields[13] else 0
        high = abs(int(fields[8])) if fields[8] else 0
        low = abs(int(fields[9])) if fields[9] else 0
        open_ = abs(int(fields[7])) if fields[7] else 0

        return {
            "code": code,
            "price": price,
            "change_rate": change_rate,
            "volume": volume,
            "high": high,
            "low": low,
            "open": open_,
            "trade_time": fields[1],
        }
    except Exception:
        return None


class KISWebSocket:
    """
    KIS WebSocket 실시간 시세 수신기
    구독한 종목의 체결 데이터를 실시간으로 수신하고 콜백으로 전달합니다.
    """

    def __init__(self):
        self.auth = get_auth()
        self.ws_url = KIS_VIRTUAL_WS_URL if KIS_IS_VIRTUAL else KIS_WS_URL
        self._subscribed_codes: set[str] = set()
        self._on_update: Optional[Callable[[dict], None]] = None
        self._price_cache: dict[str, dict] = {}  # code → 최신 시세
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws = None

    def set_callback(self, callback: Callable[[dict], None]):
        """실시간 업데이트 콜백 등록"""
        self._on_update = callback

    def subscribe(self, codes: list[str]):
        """종목 구독 추가"""
        new_codes = set(codes) - self._subscribed_codes
        self._subscribed_codes.update(new_codes)

        if self._ws and new_codes:
            for code in new_codes:
                asyncio.run_coroutine_threadsafe(
                    self._send_subscribe(code), self._loop
                )

    def start(self):
        """WebSocket 수신 스레드 시작"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self._thread.start()
        logger.info("KIS WebSocket 시작")

    def stop(self):
        """WebSocket 종료"""
        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        logger.info("KIS WebSocket 종료")

    def get_cached_price(self, code: str) -> Optional[dict]:
        """캐시된 최신 시세 반환"""
        return self._price_cache.get(code)

    def get_all_cached(self) -> dict[str, dict]:
        """캐시된 모든 시세 반환"""
        return self._price_cache.copy()

    # ─── 내부 비동기 구현 ───────────────────────────────────────────────────────

    def _run_async_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect_loop())
        except Exception as e:
            logger.error(f"WebSocket 루프 오류: {e}")
        finally:
            self._loop.close()

    async def _connect_loop(self):
        """연결 유지 루프 (끊기면 재연결)"""
        while self._running:
            try:
                await self._connect()
            except Exception as e:
                logger.warning(f"WebSocket 연결 끊김: {e}. 5초 후 재연결...")
                if self._running:
                    await asyncio.sleep(5)

    async def _connect(self):
        """WebSocket 연결 및 메시지 수신"""
        approval_key = self.auth.get_ws_approval_key()
        if not approval_key:
            logger.error("WebSocket 접속키 발급 실패")
            await asyncio.sleep(10)
            return

        async with websockets.connect(
            self.ws_url,
            ping_interval=30,
            ping_timeout=10,
        ) as ws:
            self._ws = ws
            logger.info(f"KIS WebSocket 연결됨: {self.ws_url}")

            # 기존 구독 종목 재등록
            for code in self._subscribed_codes:
                await self._send_subscribe(code)

            # 메시지 수신 루프
            async for message in ws:
                if not self._running:
                    break
                await self._handle_message(message)

        self._ws = None

    async def _send_subscribe(self, code: str):
        """종목 구독 메시지 전송"""
        if not self._ws:
            return

        msg = {
            "header": {
                "approval_key": self.auth.get_ws_approval_key(),
                "custtype": "P",
                "tr_type": "1",  # 1=등록
                "content-type": "utf-8",
            },
            "body": {
                "input": {
                    "tr_id": "H0STCNT0",      # 주식 실시간 체결
                    "tr_key": code,
                }
            },
        }
        await self._ws.send(json.dumps(msg))

    async def _handle_message(self, message: str):
        """수신 메시지 처리"""
        # PINGPONG 처리
        if message.startswith("PINGPONG"):
            if self._ws:
                await self._ws.send("PONGPING")
            return

        # JSON 응답 (구독 성공/실패 등)
        if message.startswith("{"):
            try:
                data = json.loads(message)
                rt_cd = data.get("header", {}).get("tr_id", "")
                body = data.get("body", {})
                if body.get("rt_cd") == "1":
                    logger.warning(f"구독 실패: {body.get('msg1', '')}")
            except Exception:
                pass
            return

        # 실시간 시세 파싱
        parsed = _parse_realtime(message)
        if parsed:
            code = parsed["code"]
            self._price_cache[code] = parsed
            if self._on_update:
                self._on_update(parsed)


# 싱글턴
_ws_instance: Optional[KISWebSocket] = None


def get_websocket() -> KISWebSocket:
    global _ws_instance
    if _ws_instance is None:
        _ws_instance = KISWebSocket()
    return _ws_instance
