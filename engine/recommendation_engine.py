"""
추천 엔진
규칙 기반 사전 필터링 → Claude AI 최종 분석의 2단계 추천 파이프라인.
"""

import logging
import threading
import time
from typing import Callable, Optional

from config import REFRESH_INTERVAL, MAX_RECOMMENDATIONS, MIN_TRADE_AMOUNT
from engine.stock_scorer import filter_candidates
from youtube.principle_extractor import analyze_stocks_with_principles, load_principles_from_db
from kiwoom.kiwoom_bridge import get_bridge

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """
    실시간 종목 추천 엔진.

    흐름:
    1. KiwoomBridge에서 실시간 시세 수신
    2. StockScorer로 규칙 기반 1차 필터 (전체 → 상위 50개)
    3. Claude API로 2차 AI 분석 (50개 → 추천 10개)
    4. 결과를 콜백으로 UI에 전달
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
        self._ai_call_interval = 60  # AI는 1분마다 호출 (API 비용 절약)

    def load_principles(self) -> bool:
        """DB에서 투자 원칙 로드"""
        self.principles = load_principles_from_db(self.channel_url)
        if self.principles:
            logger.info(f"{len(self.principles)}개 투자 원칙 로드 완료")
            return True
        logger.warning("로드된 투자 원칙이 없습니다. 채널 분석을 먼저 실행하세요.")
        return False

    def set_callbacks(
        self,
        on_update: Callable[[list[dict]], None],
        on_error: Optional[Callable[[str], None]] = None,
    ):
        """UI 콜백 등록"""
        self._on_update = on_update
        self._on_error = on_error

    def start(self):
        """백그라운드 추천 루프 시작"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("추천 엔진 시작")

    def stop(self):
        """추천 루프 중지"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("추천 엔진 중지")

    def _run_loop(self):
        """메인 추천 루프 (백그라운드 스레드)"""
        bridge = get_bridge()
        consecutive_errors = 0

        while self._running:
            try:
                if not self.principles:
                    if not self.load_principles():
                        time.sleep(REFRESH_INTERVAL)
                        continue

                # 1단계: 실시간 시세 수신
                logger.debug("시세 데이터 수신 중...")
                all_stocks = bridge.get_market_data(max_stocks=300)

                if not all_stocks:
                    logger.warning("시세 데이터를 받지 못했습니다.")
                    time.sleep(REFRESH_INTERVAL)
                    continue

                # 최소 거래대금 필터 (너무 소형주 제외)
                all_stocks = [
                    s for s in all_stocks
                    if s.get("price", 0) * s.get("volume", 0) >= MIN_TRADE_AMOUNT
                ]

                # 2단계: 규칙 기반 1차 필터
                candidates = filter_candidates(
                    all_stocks,
                    self.principles,
                    min_score=20,
                    top_n=50,
                )
                logger.debug(f"1차 필터: {len(all_stocks)}개 → {len(candidates)}개 후보")

                # 3단계: AI 분석 (1분 간격으로 제한)
                now = time.time()
                if now - self._last_ai_call >= self._ai_call_interval and candidates:
                    logger.info(f"Claude AI 분석 시작 ({len(candidates)}개 후보)")
                    ai_results = analyze_stocks_with_principles(
                        self.principles, candidates[:50]
                    )
                    self._last_ai_call = now

                    if ai_results:
                        # AI 결과에 규칙 점수 병합
                        scored_map = {c["code"]: c for c in candidates}
                        for rec in ai_results:
                            code = rec.get("code", "")
                            if code in scored_map:
                                rec["rule_score"] = scored_map[code].get("rule_score", 0)
                                rec["price"] = scored_map[code].get("price", 0)
                                rec["change_rate"] = scored_map[code].get("change_rate", 0)
                                rec["volume"] = scored_map[code].get("volume", 0)

                        # BUY 우선, 점수 내림차순
                        ai_results.sort(
                            key=lambda x: (x.get("action") == "BUY", x.get("score", 0)),
                            reverse=True,
                        )
                        self.current_recommendations = ai_results[:MAX_RECOMMENDATIONS]
                    else:
                        # AI 실패 시 규칙 기반 결과만 사용
                        self.current_recommendations = self._make_rule_based_results(
                            candidates[:MAX_RECOMMENDATIONS]
                        )
                else:
                    # AI 호출 간격 사이에는 규칙 기반 결과 갱신
                    if candidates:
                        self.current_recommendations = self._make_rule_based_results(
                            candidates[:MAX_RECOMMENDATIONS]
                        )

                if self._on_update and self.current_recommendations:
                    self._on_update(self.current_recommendations)

                consecutive_errors = 0

            except Exception as e:
                consecutive_errors += 1
                logger.error(f"추천 엔진 오류 (연속 {consecutive_errors}회): {e}")
                if self._on_error:
                    self._on_error(str(e))
                if consecutive_errors >= 5:
                    logger.critical("연속 오류 5회. 추천 엔진 중지.")
                    break

            time.sleep(REFRESH_INTERVAL)

    def _make_rule_based_results(self, candidates: list[dict]) -> list[dict]:
        """규칙 기반 결과를 AI 결과 형식으로 변환"""
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
                "reason": " | ".join(reasons) if reasons else "원칙 조건 부합",
                "principle_titles": principle_titles,
                "action": "WATCH",  # 규칙 기반은 WATCH로 표시
                "caution": "AI 분석 대기 중",
                "source": "rule",
            })
        return results

    def _get_principle_titles(self, principle_ids: list[str]) -> list[str]:
        """원칙 ID → 제목 변환"""
        id_map = {p["id"]: p["title"] for p in self.principles}
        return [id_map.get(pid, pid) for pid in principle_ids]

    def get_recommendations(self) -> list[dict]:
        """현재 추천 목록 반환"""
        return self.current_recommendations.copy()
