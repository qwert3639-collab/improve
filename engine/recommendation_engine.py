"""
추천 엔진 (KIS API 버전)
규칙 기반 사전 필터링 → Claude AI 최종 분석의 2단계 추천 파이프라인.
Kiwoom COM 브릿지 없이 KIS REST API로 직접 시세 수신.
"""

import logging
import threading
import time
from typing import Callable, Optional

from config import REFRESH_INTERVAL, MAX_RECOMMENDATIONS, MIN_TRADE_AMOUNT
from engine.stock_scorer import filter_candidates
from youtube.principle_extractor import analyze_stocks_with_principles, load_principles_from_db
from kis.kis_client import get_client
from kis.kis_websocket import get_websocket

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """
    실시간 종목 추천 엔진 (KIS API 기반)

    흐름:
    1. KIS REST API로 거래량/등락률 상위 종목 수집
    2. WebSocket으로 구독 종목 실시간 시세 갱신
    3. StockScorer로 규칙 기반 1차 필터 (→ 상위 50개)
    4. Claude AI 2차 분석 (→ 최종 추천 10개)
    5. 결과를 콜백으로 UI에 전달
    """

    def __init__(self, channel_url: str = ""):
        self.channel_url = channel_url
        self.principles: list[dict] = []
        self.current_recommendations: list[dict] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._on_update: Optional[Callable[[list[dict]], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None
        self._last_ai_call = 0
        self._ai_call_interval = 15 * 60  # AI는 15분마다 (비용 절약 - 월 ~$4 수준)
        self._market_cache: list[dict] = []
        self._market_cache_time = 0.0
        self._market_cache_ttl = 30  # 시장 데이터 캐시 30초

    def load_principles(self) -> bool:
        """DB에서 투자 원칙 로드"""
        self.principles = load_principles_from_db(self.channel_url)
        if self.principles:
            logger.info(f"{len(self.principles)}개 투자 원칙 로드 완료")
            return True
        logger.warning("투자 원칙 없음. 채널 분석을 먼저 실행하세요.")
        return False

    def set_callbacks(
        self,
        on_update: Callable[[list[dict]], None],
        on_error: Optional[Callable[[str], None]] = None,
    ):
        self._on_update = on_update
        self._on_error = on_error

    def start(self):
        """백그라운드 추천 루프 시작"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        # WebSocket 실시간 구독 시작
        ws = get_websocket()
        ws.set_callback(self._on_realtime_update)
        ws.start()

        logger.info("추천 엔진 시작 (KIS API)")

    def stop(self):
        """추천 루프 중지"""
        self._running = False
        get_websocket().stop()
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("추천 엔진 중지")

    def _on_realtime_update(self, data: dict):
        """WebSocket 실시간 시세 수신 → 캐시 갱신"""
        code = data.get("code", "")
        if not code or not self._market_cache:
            return
        # 캐시에 있는 종목이면 시세 업데이트
        for stock in self._market_cache:
            if stock.get("code") == code:
                stock.update({
                    "price": data.get("price", stock.get("price", 0)),
                    "change_rate": data.get("change_rate", stock.get("change_rate", 0)),
                    "volume": data.get("volume", stock.get("volume", 0)),
                    "high": data.get("high", stock.get("high", 0)),
                    "low": data.get("low", stock.get("low", 0)),
                })
                break

    def _get_market_data(self) -> list[dict]:
        """시장 데이터 조회 (캐시 활용)"""
        now = time.time()
        if self._market_cache and (now - self._market_cache_time) < self._market_cache_ttl:
            return self._market_cache

        client = get_client()
        stocks = client.get_market_data(max_stocks=200)

        if stocks:
            self._market_cache = stocks
            self._market_cache_time = now
            # 상위 종목 WebSocket 구독
            codes = [s["code"] for s in stocks[:50] if s.get("code")]
            get_websocket().subscribe(codes)

        return stocks

    def _run_loop(self):
        """메인 추천 루프 (백그라운드 스레드)"""
        consecutive_errors = 0

        while self._running:
            try:
                if not self.principles:
                    if not self.load_principles():
                        time.sleep(REFRESH_INTERVAL)
                        continue

                # 1단계: 시장 데이터 수집 (캐시 or 신규 조회)
                all_stocks = self._get_market_data()
                if not all_stocks:
                    logger.warning("시장 데이터 없음")
                    time.sleep(REFRESH_INTERVAL)
                    continue

                # 최소 거래대금 필터
                filtered = [
                    s for s in all_stocks
                    if s.get("trade_amount", s.get("price", 0) * s.get("volume", 0)) >= MIN_TRADE_AMOUNT
                ]

                # 2단계: 규칙 기반 1차 필터
                candidates = filter_candidates(
                    filtered,
                    self.principles,
                    min_score=20,
                    top_n=50,
                )
                logger.debug(f"1차 필터: {len(filtered)}개 → {len(candidates)}개 후보")

                # 3단계: Claude AI 분석 (1분 간격)
                now = time.time()
                if now - self._last_ai_call >= self._ai_call_interval and candidates:
                    logger.info(f"Claude AI 분석 ({len(candidates)}개 후보)")
                    ai_results = analyze_stocks_with_principles(
                        self.principles, candidates[:50]
                    )
                    self._last_ai_call = now

                    if ai_results:
                        scored_map = {c["code"]: c for c in candidates}
                        for rec in ai_results:
                            code = rec.get("code", "")
                            if code in scored_map:
                                rec.update({
                                    "rule_score": scored_map[code].get("rule_score", 0),
                                    "price": scored_map[code].get("price", 0),
                                    "change_rate": scored_map[code].get("change_rate", 0),
                                    "volume": scored_map[code].get("volume", 0),
                                })

                        ai_results.sort(
                            key=lambda x: (x.get("action") == "BUY", x.get("score", 0)),
                            reverse=True,
                        )
                        self.current_recommendations = ai_results[:MAX_RECOMMENDATIONS]
                    else:
                        self.current_recommendations = self._make_rule_based_results(
                            candidates[:MAX_RECOMMENDATIONS]
                        )
                elif candidates and not self.current_recommendations:
                    self.current_recommendations = self._make_rule_based_results(
                        candidates[:MAX_RECOMMENDATIONS]
                    )
                elif candidates:
                    # WebSocket으로 받은 최신 시세로 기존 추천 가격만 갱신
                    ws = get_websocket()
                    for rec in self.current_recommendations:
                        cached = ws.get_cached_price(rec.get("code", ""))
                        if cached:
                            rec["price"] = cached.get("price", rec["price"])
                            rec["change_rate"] = cached.get("change_rate", rec["change_rate"])
                            rec["volume"] = cached.get("volume", rec["volume"])

                if self._on_update and self.current_recommendations:
                    self._on_update(self.current_recommendations)

                consecutive_errors = 0

            except Exception as e:
                consecutive_errors += 1
                logger.error(f"추천 엔진 오류 (연속 {consecutive_errors}회): {e}")
                if self._on_error:
                    self._on_error(str(e))
                if consecutive_errors >= 5:
                    logger.critical("연속 오류 5회. 엔진 중지.")
                    break

            time.sleep(REFRESH_INTERVAL)

    def _make_rule_based_results(self, candidates: list[dict]) -> list[dict]:
        """규칙 기반 결과를 추천 형식으로 변환"""
        results = []
        for c in candidates:
            reasons = c.get("match_reasons", [])
            principles_matched = c.get("matched_principles", [])
            principle_titles = self._get_principle_titles(principles_matched)

            results.append({
                "code": c.get("code", ""),
                "name": c.get("name", ""),
                "score": c.get("rule_score", 0),
                "price": c.get("price", 0),
                "change_rate": c.get("change_rate", 0),
                "volume": c.get("volume", 0),
                "matched_principles": principles_matched,
                "reason": " | ".join(reasons) if reasons else "투자 원칙 조건 부합",
                "principle_titles": principle_titles,
                "action": "WATCH",
                "caution": "AI 분석 대기 중",
                "source": "rule",
            })
        return results

    def _get_principle_titles(self, principle_ids: list[str]) -> list[str]:
        id_map = {p["id"]: p["title"] for p in self.principles}
        return [id_map.get(pid, pid) for pid in principle_ids]

    def get_recommendations(self) -> list[dict]:
        return self.current_recommendations.copy()
