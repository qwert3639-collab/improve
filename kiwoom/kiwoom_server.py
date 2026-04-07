"""
키움 OpenAPI 서버 (32비트 Python 전용)
이 파일은 반드시 32비트 Python으로 실행해야 합니다.
  py -3.8-32 kiwoom/kiwoom_server.py

키움 COM 오브젝트에 접근하고, 로컬 소켓으로 64비트 메인 프로세스와 통신합니다.
"""

import sys
import socket
import json
import logging
import time
import threading
from datetime import datetime

# 32비트 환경 체크
if sys.maxsize > 2**32:
    print("[경고] 이 서버는 32비트 Python으로 실행해야 합니다.")
    print("명령어: py -3.8-32 kiwoom/kiwoom_server.py")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [KiwoomServer] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("kiwoom_server.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

HOST = "127.0.0.1"
PORT = 9999

# 키움 에러 코드 → 메시지
KIWOOM_ERRORS = {
    0: "정상",
    -100: "사용자 정보교환 실패",
    -101: "서버 접속 실패",
    -102: "버전처리 실패",
    -200: "시세조회 과부하",
    -201: "REQUEST_INPUT_st 세팅 오류",
}


class KiwoomWrapper:
    """키움 OpenAPI+ COM 오브젝트 래퍼"""

    def __init__(self):
        self.kiwoom = None
        self.connected = False
        self._login_event = threading.Event()
        self._tr_event = threading.Event()
        self._tr_data = {}

    def connect(self) -> bool:
        """키움 로그인 및 연결"""
        try:
            from PyQt5.QAxContainer import QAxWidget
            from PyQt5.QtWidgets import QApplication

            if not QApplication.instance():
                self.app = QApplication(sys.argv)

            self.kiwoom = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
            self.kiwoom.OnEventConnect.connect(self._on_event_connect)
            self.kiwoom.OnReceiveTrData.connect(self._on_receive_tr_data)

            logger.info("키움 로그인 시도 중...")
            self.kiwoom.dynamicCall("CommConnect()")

            # 로그인 대기 (최대 60초)
            if not self._login_event.wait(timeout=60):
                logger.error("로그인 타임아웃")
                return False

            return self.connected

        except ImportError:
            logger.error("PyQt5 또는 키움 OpenAPI가 설치되지 않았습니다.")
            logger.error("setup/install_32bit.bat 를 먼저 실행하세요.")
            return False
        except Exception as e:
            logger.error(f"연결 오류: {e}")
            return False

    def _on_event_connect(self, err_code: int):
        if err_code == 0:
            self.connected = True
            user_id = self.kiwoom.dynamicCall("GetLoginInfo(QString)", "USER_ID")
            logger.info(f"키움 로그인 성공: {user_id}")
        else:
            msg = KIWOOM_ERRORS.get(err_code, f"알 수 없는 오류 ({err_code})")
            logger.error(f"키움 로그인 실패: {msg}")
        self._login_event.set()

    def _on_receive_tr_data(self, screen_no, rqname, trcode, record_name, prev_next, *args):
        """TR 데이터 수신 이벤트"""
        self._tr_data[rqname] = {
            "screen_no": screen_no,
            "trcode": trcode,
            "record_name": record_name,
            "prev_next": prev_next,
        }
        self._tr_event.set()

    def get_stock_price(self, code: str) -> dict:
        """단일 종목 현재가 조회 (opt10001 TR)"""
        if not self.connected:
            return {}

        try:
            rqname = f"주식기본정보_{code}"
            self._tr_event.clear()

            self.kiwoom.dynamicCall(
                "SetInputValue(QString, QString)", "종목코드", code
            )
            self.kiwoom.dynamicCall(
                "CommRqData(QString, QString, int, QString)",
                rqname, "opt10001", 0, "0101",
            )

            if not self._tr_event.wait(timeout=5):
                return {}

            def get_data(field):
                return self.kiwoom.dynamicCall(
                    "GetCommData(QString, QString, int, QString)",
                    "opt10001", rqname, 0, field,
                ).strip()

            price_str = get_data("현재가").lstrip("+-")
            prev_close_str = get_data("기준가").lstrip("+-")

            price = abs(int(price_str)) if price_str else 0
            prev_close = abs(int(prev_close_str)) if prev_close_str else 0
            change_rate = ((price - prev_close) / prev_close * 100) if prev_close else 0

            return {
                "code": code,
                "name": get_data("종목명"),
                "price": price,
                "prev_close": prev_close,
                "change_rate": round(change_rate, 2),
                "volume": int(get_data("거래량").lstrip("+-") or 0),
                "high": abs(int(get_data("고가").lstrip("+-") or 0)),
                "low": abs(int(get_data("저가").lstrip("+-") or 0)),
                "open": abs(int(get_data("시가").lstrip("+-") or 0)),
                "market_cap": int(get_data("시가총액").lstrip("+-") or 0),
                "per": float(get_data("PER") or 0),
                "pbr": float(get_data("PBR") or 0),
            }
        except Exception as e:
            logger.error(f"현재가 조회 오류 {code}: {e}")
            return {}

    def get_stock_list(self, market: str = "0") -> list[str]:
        """
        전체 종목 코드 목록 반환
        market: "0"=KOSPI, "10"=KOSDAQ, "3"=ELW, "8"=ETF
        """
        try:
            codes_str = self.kiwoom.dynamicCall(
                "GetCodeListByMarket(QString)", market
            )
            return [c for c in codes_str.split(";") if c.strip()]
        except Exception as e:
            logger.error(f"종목 목록 조회 오류: {e}")
            return []

    def get_multiple_prices(self, codes: list[str]) -> list[dict]:
        """여러 종목 현재가 일괄 조회"""
        results = []
        for code in codes:
            data = self.get_stock_price(code)
            if data:
                results.append(data)
            time.sleep(0.1)  # TR 과부하 방지
        return results


class KiwoomSocketServer:
    """64비트 메인 프로세스와 통신하는 소켓 서버"""

    def __init__(self, kiwoom: KiwoomWrapper):
        self.kiwoom = kiwoom
        self.server_socket = None
        self.running = False

    def start(self):
        """소켓 서버 시작"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((HOST, PORT))
        self.server_socket.listen(5)
        self.running = True
        logger.info(f"키움 소켓 서버 시작: {HOST}:{PORT}")

        while self.running:
            try:
                client_sock, addr = self.server_socket.accept()
                thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_sock,),
                    daemon=True,
                )
                thread.start()
            except Exception as e:
                if self.running:
                    logger.error(f"소켓 오류: {e}")

    def _handle_client(self, client_sock: socket.socket):
        """클라이언트 요청 처리"""
        try:
            data = b""
            while True:
                chunk = client_sock.recv(4096)
                if not chunk:
                    break
                data += chunk
                if data.endswith(b"\n"):
                    break

            request = json.loads(data.decode("utf-8"))
            action = request.get("action", "")

            if action == "ping":
                response = {"status": "ok", "connected": self.kiwoom.connected}

            elif action == "get_price":
                code = request.get("code", "")
                result = self.kiwoom.get_stock_price(code)
                response = {"status": "ok", "data": result}

            elif action == "get_prices":
                codes = request.get("codes", [])
                results = self.kiwoom.get_multiple_prices(codes)
                response = {"status": "ok", "data": results}

            elif action == "get_stock_list":
                market = request.get("market", "0")
                codes = self.kiwoom.get_stock_list(market)
                response = {"status": "ok", "data": codes}

            elif action == "get_market_data":
                # KOSPI + KOSDAQ 주요 종목 현재가
                kospi = self.kiwoom.get_stock_list("0")[:100]
                kosdaq = self.kiwoom.get_stock_list("10")[:100]
                all_codes = kospi + kosdaq
                results = self.kiwoom.get_multiple_prices(all_codes)
                response = {"status": "ok", "data": results}

            else:
                response = {"status": "error", "message": f"알 수 없는 action: {action}"}

            client_sock.sendall(json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n")

        except Exception as e:
            logger.error(f"클라이언트 처리 오류: {e}")
            try:
                error_resp = {"status": "error", "message": str(e)}
                client_sock.sendall(json.dumps(error_resp).encode("utf-8") + b"\n")
            except Exception:
                pass
        finally:
            client_sock.close()

    def stop(self):
        self.running = False
        if self.server_socket:
            self.server_socket.close()


def main():
    logger.info("=" * 50)
    logger.info("키움 OpenAPI 서버 시작")
    logger.info("=" * 50)

    kiwoom = KiwoomWrapper()

    if not kiwoom.connect():
        logger.error("키움 연결 실패. 서버를 종료합니다.")
        logger.error("HTS가 실행 중이고 로그인된 상태인지 확인하세요.")
        sys.exit(1)

    server = KiwoomSocketServer(kiwoom)

    try:
        server.start()
    except KeyboardInterrupt:
        logger.info("서버 종료 중...")
        server.stop()


if __name__ == "__main__":
    main()
