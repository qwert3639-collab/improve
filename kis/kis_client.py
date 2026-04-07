"""
KIS REST API 클라이언트
한국투자증권 OpenAPI - 시세 조회, 종목 스크리닝 담당
HTS 없이 64비트 Python에서 직접 HTTP 요청
"""

import logging
import time
from typing import Optional

import requests

from config import KIS_IS_VIRTUAL, KIS_BASE_URL, KIS_VIRTUAL_BASE_URL
from kis.kis_auth import get_auth

logger = logging.getLogger(__name__)

# TR 요청 간 최소 딜레이 (초) - KIS는 초당 20건 제한
TR_DELAY = 0.06


class KISClient:
    """
    KIS REST API 클라이언트
    시세 조회, 종목 목록, 랭킹 등 조회 기능 제공
    """

    def __init__(self):
        self.auth = get_auth()
        self.base_url = KIS_VIRTUAL_BASE_URL if KIS_IS_VIRTUAL else KIS_BASE_URL
        self._last_request_time = 0.0

    def _get(self, path: str, tr_id: str, params: dict) -> Optional[dict]:
        """GET 요청 공통 처리"""
        # Rate limiting
        elapsed = time.time() - self._last_request_time
        if elapsed < TR_DELAY:
            time.sleep(TR_DELAY - elapsed)

        url = f"{self.base_url}{path}"
        headers = self.auth.get_headers(tr_id)

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            self._last_request_time = time.time()
            resp.raise_for_status()
            data = resp.json()

            rt_cd = data.get("rt_cd", "")
            if rt_cd != "0":
                msg = data.get("msg1", "알 수 없는 오류")
                logger.warning(f"KIS API 오류 [{tr_id}] rt_cd={rt_cd}: {msg}")
                return None

            return data

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                # 토큰 만료 - 강제 재발급 후 1회 재시도
                logger.warning("토큰 만료. 재발급 후 재시도...")
                self.auth._access_token = ""
                try:
                    resp = requests.get(url, headers=self.auth.get_headers(tr_id), params=params, timeout=10)
                    resp.raise_for_status()
                    return resp.json()
                except Exception as e2:
                    logger.error(f"재시도 실패: {e2}")
            else:
                logger.error(f"HTTP {e.response.status_code}: {e.response.text[:200]}")
            return None
        except Exception as e:
            logger.error(f"요청 오류 [{tr_id}]: {e}")
            return None

    # ─── 시세 조회 ────────────────────────────────────────────────────────────

    def get_stock_price(self, code: str) -> Optional[dict]:
        """
        단일 종목 현재가 조회
        TR: FHKST01010100 (주식현재가시세)
        """
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            tr_id="FHKST01010100",
            params={
                "fid_cond_mrkt_div_code": "J",  # J=주식
                "fid_input_iscd": code,
            },
        )
        if not data:
            return None

        output = data.get("output", {})
        if not output:
            return None

        try:
            price = abs(int(output.get("stck_prpr", 0)))          # 현재가
            prev_close = abs(int(output.get("stck_sdpr", 0)))     # 전일 종가
            change_rate = float(output.get("prdy_ctrt", 0))       # 전일대비율
            volume = int(output.get("acml_vol", 0))               # 누적거래량
            high = abs(int(output.get("stck_hgpr", 0)))           # 고가
            low = abs(int(output.get("stck_lwpr", 0)))            # 저가
            open_ = abs(int(output.get("stck_oprc", 0)))          # 시가
            per = float(output.get("per", 0) or 0)
            pbr = float(output.get("pbr", 0) or 0)
            mktcap = int(output.get("hts_avls", 0) or 0)         # 시가총액(억)

            return {
                "code": code,
                "name": output.get("hts_kor_isnm", ""),
                "price": price,
                "prev_close": prev_close,
                "change_rate": change_rate,
                "volume": volume,
                "high": high,
                "low": low,
                "open": open_,
                "per": per,
                "pbr": pbr,
                "market_cap_billion": mktcap,
                "trade_amount": price * volume,  # 거래대금 추정
            }
        except (ValueError, TypeError) as e:
            logger.warning(f"시세 파싱 오류 {code}: {e}")
            return None

    def get_multiple_prices(
        self,
        codes: list[str],
        progress_callback=None,
    ) -> list[dict]:
        """여러 종목 현재가 일괄 조회"""
        results = []
        total = len(codes)

        for i, code in enumerate(codes):
            if progress_callback:
                progress_callback(i + 1, total, f"시세 조회 중 ({i+1}/{total})")

            data = self.get_stock_price(code)
            if data:
                results.append(data)

        return results

    # ─── 랭킹/스크리닝 ──────────────────────────────────────────────────────────

    def get_volume_ranking(self, market: str = "ALL", top_n: int = 100) -> list[dict]:
        """
        거래량 상위 종목 조회
        TR: FHPST01710000
        market: "J"=전체, "0"=KOSPI, "Q"=KOSDAQ
        """
        market_code = {"ALL": "0", "KOSPI": "0", "KOSDAQ": "Q"}.get(market, "0")

        data = self._get(
            "/uapi/domestic-stock/v1/ranking/volume",
            tr_id="FHPST01710000",
            params={
                "fid_cond_mrkt_div_code": "J",
                "fid_cond_scr_div_code": "20171",
                "fid_input_iscd": market_code,
                "fid_div_cls_code": "0",        # 0=전체
                "fid_blng_cls_code": "0",
                "fid_trgt_cls_code": "111111111",
                "fid_trgt_exls_cls_code": "0000000000",
                "fid_input_price_1": "",
                "fid_input_price_2": "",
                "fid_vol_cnt": "",
                "fid_input_date_1": "",
            },
        )

        if not data:
            return []

        results = []
        for item in data.get("output", [])[:top_n]:
            try:
                price = abs(int(item.get("stck_prpr", 0) or 0))
                volume = int(item.get("acml_vol", 0) or 0)
                change_rate = float(item.get("prdy_ctrt", 0) or 0)
                results.append({
                    "code": item.get("mksc_shrn_iscd", ""),
                    "name": item.get("hts_kor_isnm", ""),
                    "price": price,
                    "change_rate": change_rate,
                    "volume": volume,
                    "trade_amount": price * volume,
                    "per": float(item.get("per", 0) or 0),
                    "pbr": float(item.get("pbr", 0) or 0),
                    "market_cap_billion": int(item.get("hts_avls", 0) or 0),
                    "high": abs(int(item.get("stck_hgpr", 0) or 0)),
                    "low": abs(int(item.get("stck_lwpr", 0) or 0)),
                    "open": abs(int(item.get("stck_oprc", 0) or 0)),
                })
            except (ValueError, TypeError):
                continue

        return results

    def get_price_ranking(self, rank_type: str = "rise", top_n: int = 100) -> list[dict]:
        """
        등락률 상위/하위 종목 조회
        rank_type: "rise"=상승률, "fall"=하락률
        TR: FHPST01700000
        """
        tr_id = "FHPST01700000"
        sort_code = "0" if rank_type == "rise" else "1"

        data = self._get(
            "/uapi/domestic-stock/v1/ranking/fluctuation",
            tr_id=tr_id,
            params={
                "fid_cond_mrkt_div_code": "J",
                "fid_cond_scr_div_code": "20170",
                "fid_input_iscd": "0000",
                "fid_rank_sort_cls_code": sort_code,
                "fid_input_cnt_1": "0",
                "fid_prc_cls_code": "1",
                "fid_input_price_1": "",
                "fid_input_price_2": "",
                "fid_vol_cnt": "100000",   # 최소 거래량 10만주
                "fid_trgt_cls_code": "0",
                "fid_trgt_exls_cls_code": "0",
                "fid_div_cls_code": "0",
                "fid_rsfl_rate1": "",
                "fid_rsfl_rate2": "",
            },
        )

        if not data:
            return []

        results = []
        for item in data.get("output", [])[:top_n]:
            try:
                price = abs(int(item.get("stck_prpr", 0) or 0))
                volume = int(item.get("acml_vol", 0) or 0)
                results.append({
                    "code": item.get("mksc_shrn_iscd", ""),
                    "name": item.get("hts_kor_isnm", ""),
                    "price": price,
                    "change_rate": float(item.get("prdy_ctrt", 0) or 0),
                    "volume": volume,
                    "trade_amount": price * volume,
                    "per": float(item.get("per", 0) or 0),
                    "pbr": float(item.get("pbr", 0) or 0),
                    "market_cap_billion": 0,
                    "high": 0,
                    "low": 0,
                    "open": 0,
                })
            except (ValueError, TypeError):
                continue

        return results

    def get_market_data(self, max_stocks: int = 200) -> list[dict]:
        """
        스크리닝용 시장 전체 데이터 수집
        거래량 상위 + 등락률 상위를 합쳐서 반환
        """
        per_category = max_stocks // 3

        logger.info("KIS 시장 데이터 수집 중...")
        volume_top = self.get_volume_ranking(top_n=per_category * 2)
        rise_top = self.get_price_ranking("rise", top_n=per_category)

        # 중복 제거
        seen = set()
        merged = []
        for stock in volume_top + rise_top:
            code = stock.get("code", "")
            if code and code not in seen:
                seen.add(code)
                merged.append(stock)

        logger.info(f"시장 데이터 수집 완료: {len(merged)}개 종목")
        return merged[:max_stocks]

    def verify_connection(self) -> bool:
        """연결 테스트 - 삼성전자(005930) 현재가 조회"""
        try:
            result = self.get_stock_price("005930")
            if result and result.get("price", 0) > 0:
                logger.info(f"KIS 연결 확인: 삼성전자 {result['price']:,}원")
                return True
            return False
        except Exception as e:
            logger.error(f"KIS 연결 확인 실패: {e}")
            return False


# 싱글턴
_client_instance: Optional[KISClient] = None


def get_client() -> KISClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = KISClient()
    return _client_instance
