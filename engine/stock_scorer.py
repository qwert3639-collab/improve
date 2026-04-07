"""
종목 스코어러
투자 원칙과 실시간 종목 데이터를 대조하여 규칙 기반 점수를 산출합니다.
Claude API 호출 없이 빠르게 사전 필터링하는 역할을 담당합니다.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


# ─── 원칙 키워드 → 체크 함수 매핑 ─────────────────────────────────────────────

def _check_volume_surge(stock: dict, threshold: float = 2.0) -> float:
    """거래량 급증 체크. 평소 대비 threshold배 이상이면 1.0점"""
    # 키움에서 거래량 급증 비율을 직접 주지 않으므로,
    # 일단 거래량이 클수록 점수를 줌 (상대적 평가는 추후 개선)
    volume = stock.get("volume", 0)
    if volume > 5_000_000:
        return 1.0
    elif volume > 1_000_000:
        return 0.6
    elif volume > 500_000:
        return 0.3
    return 0.0


def _check_price_rise(stock: dict, min_rate: float = 3.0) -> float:
    """상승률 체크"""
    rate = stock.get("change_rate", 0)
    if rate >= min_rate * 2:
        return 1.0
    elif rate >= min_rate:
        return 0.7
    elif rate > 0:
        return 0.3
    return 0.0


def _check_near_52w_high(stock: dict, threshold: float = 0.95) -> float:
    """52주 신고가 근처 체크 (데이터가 있을 경우)"""
    high_52w = stock.get("high_52w", 0)
    price = stock.get("price", 0)
    if high_52w and price:
        ratio = price / high_52w
        if ratio >= 0.98:
            return 1.0
        elif ratio >= threshold:
            return 0.6
    return 0.0


def _check_low_per(stock: dict, max_per: float = 15.0) -> float:
    """저PER 체크"""
    per = stock.get("per", 0)
    if 0 < per <= max_per * 0.5:
        return 1.0
    elif 0 < per <= max_per:
        return 0.6
    return 0.0


def _check_low_pbr(stock: dict, max_pbr: float = 1.0) -> float:
    """저PBR 체크"""
    pbr = stock.get("pbr", 0)
    if 0 < pbr <= max_pbr * 0.5:
        return 1.0
    elif 0 < pbr <= max_pbr:
        return 0.6
    return 0.0


def _check_rebound(stock: dict) -> float:
    """눌림목 반등 체크 (저가 대비 현재가 상승)"""
    price = stock.get("price", 0)
    low = stock.get("low", 0)
    if price and low and low > 0:
        rebound_rate = (price - low) / low * 100
        if rebound_rate >= 3:
            return 1.0
        elif rebound_rate >= 1:
            return 0.5
    return 0.0


# 키워드 → 체크 함수 매핑
KEYWORD_CHECKERS = {
    "거래량": _check_volume_surge,
    "급증": _check_volume_surge,
    "상승": _check_price_rise,
    "52주": _check_near_52w_high,
    "신고가": _check_near_52w_high,
    "PER": _check_low_per,
    "저평가": _check_low_per,
    "PBR": _check_low_pbr,
    "눌림목": _check_rebound,
    "반등": _check_rebound,
}


def score_stock_by_principle(stock: dict, principle: dict) -> tuple[float, list[str]]:
    """
    단일 원칙에 대해 종목의 적합도를 계산합니다.

    Returns:
        (점수 0.0~1.0, 매칭된 이유 리스트)
    """
    keywords = principle.get("keywords", [])
    conditions = principle.get("conditions", [])
    indicators = principle.get("indicators", [])

    total_score = 0.0
    matched_reasons = []
    checked = 0

    # 키워드 기반 체크
    for keyword in keywords + indicators:
        for kw, checker_fn in KEYWORD_CHECKERS.items():
            if kw in str(keyword):
                score = checker_fn(stock)
                if score > 0:
                    total_score += score
                    matched_reasons.append(f"{keyword} 조건 충족 ({score:.0%})")
                checked += 1
                break

    # 점수 정규화
    if checked > 0:
        normalized = min(total_score / checked, 1.0)
    else:
        normalized = 0.0

    return normalized, matched_reasons


def score_stock(stock: dict, principles: list[dict]) -> dict:
    """
    모든 투자 원칙에 대해 종목을 평가합니다.

    Returns:
        {
            "code": ...,
            "name": ...,
            "price": ...,
            "change_rate": ...,
            "rule_score": 0-100,  # 규칙 기반 점수
            "matched_principles": [...],
            "match_reasons": [...]
        }
    """
    matched_principles = []
    all_reasons = []
    total_score = 0.0

    for principle in principles:
        score, reasons = score_stock_by_principle(stock, principle)
        if score >= 0.5:  # 50% 이상 매칭된 원칙만 채택
            matched_principles.append(principle.get("id", ""))
            all_reasons.extend(reasons)
            total_score += score

    # 원칙 매칭 개수에 따른 가중치
    principle_bonus = min(len(matched_principles) * 10, 30)
    rule_score = int(min(total_score * 50 + principle_bonus, 100))

    return {
        "code": stock.get("code", ""),
        "name": stock.get("name", ""),
        "price": stock.get("price", 0),
        "change_rate": stock.get("change_rate", 0),
        "volume": stock.get("volume", 0),
        "per": stock.get("per", 0),
        "pbr": stock.get("pbr", 0),
        "rule_score": rule_score,
        "matched_principles": matched_principles,
        "match_reasons": list(set(all_reasons)),  # 중복 제거
    }


def filter_candidates(
    all_stocks: list[dict],
    principles: list[dict],
    min_score: int = 30,
    top_n: int = 50,
) -> list[dict]:
    """
    전체 종목에서 투자 원칙에 부합하는 후보를 사전 필터링합니다.
    Claude API 호출 전 범위를 줄이기 위한 규칙 기반 1차 필터.

    Args:
        all_stocks: 전체 종목 데이터
        principles: 투자 원칙 리스트
        min_score: 최소 점수 (이 이상만 통과)
        top_n: 반환할 최대 종목 수

    Returns:
        점수 높은 순으로 정렬된 후보 종목 리스트
    """
    scored = []
    for stock in all_stocks:
        result = score_stock(stock, principles)
        if result["rule_score"] >= min_score:
            scored.append(result)

    scored.sort(key=lambda x: x["rule_score"], reverse=True)
    return scored[:top_n]
