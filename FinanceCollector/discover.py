import os
import json
import time
import logging
import requests
from playwright.sync_api import sync_playwright
import string
from config import CONFIG 

# Thiết lập hệ thống ghi nhận lịch trình (Logging)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
LOG = logging.getLogger(__name__)

BASE_URL = "https://finance.vietstock.vn/doanh-nghiep-a-z"

def fetch_all_vietstock_tickers_automated() -> list[str]:
    """
    Giải pháp Hybrid: Mượn Playwright lấy Token/Cookie sạch, 
    sau đó dùng Requests bóc tách từng trang ở tầng Python để lấy trọn bộ thị trường.
    """
    LOG.info("[*] Khởi động trình duyệt ngầm Playwright...")
    token = ""
    cookies_list = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="vi-VN"
        )
        page = context.new_page()
        
        # Chặn tài nguyên nặng để tăng tốc độ lấy token ban đầu
        page.route("**/*", lambda route: route.abort() 
                   if route.request.resource_type in ["image", "font", "media", "stylesheet"] 
                   else route.continue_())

        LOG.info(f"[*] Đang tải trang điều hướng: {BASE_URL}")
        try:
            page.goto(BASE_URL, timeout=45000, wait_until="domcontentloaded")
            # Đợi cho token ẩn đính vào DOM
            page.wait_for_selector('input[name="__RequestVerificationToken"]', state="attached", timeout=20000)
            
            # Trích xuất Token và bộ Cookie phiên
            token = page.evaluate("() => document.querySelector('input[name=\"__RequestVerificationToken\"]').value")
            cookies_list = context.cookies()
        except Exception as e:
            LOG.error(f"[!] Không thể thiết lập phiên ban đầu qua Playwright: {e}")
            
        browser.close()
        
    if not token or not cookies_list:
        LOG.error("[-] Thất bại trong việc lấy thông tin xác thực ban đầu.")
        return []

    # FIX lỗi logic thụt lề: Đưa log và xử lý tiếp theo ra ngoài phạm vi kiểm tra lỗi rỗng
    LOG.info("[✓] Trích xuất Token và Cookie thành công. Chuyển giao sang hệ thống Python Requests...")
    
    # Định dạng lại cookie cho thư viện requests
    session_cookies = {c['name']: c['value'] for c in cookies_list}
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://finance.vietstock.vn",
        "Referer": BASE_URL
    }
    
    # Khởi tạo Session

    session = requests.Session()
    session.headers.update(headers)
    requests.utils.add_dict_to_cookiejar(session.cookies, session_cookies)
    
    all_tickers = []
    
    # Duyệt qua các catID (1:HOSE, 2:HNX, 3:OTC, 5:UPCOM, 4/6:Hủy niêm yết/Khác)
    for cat_id in ["1", "2", "5"]:
        LOG.info(f"[*] Đang quét sàn catID={cat_id} ...")
        
        # Hàng đợi ban đầu gồm các chữ cái A-Z và số 0-9
        queue = list(string.ascii_uppercase + "0123456789")
        
        while queue:
            prefix = queue.pop(0)
            
            payload = {
                "catID": cat_id,
                "industryID": "0",
                "page": "1",
                "pageSize": "50",
                "type": "0",
                "code": prefix, # Truyền tiền tố vào đây (VD: B, hoặc BA)
                "businessTypeID": "0",
                "orderBy": "Code",
                "orderDir": "ASC",
                "__RequestVerificationToken": token
            }
            
            try:
                response = session.post(
                    "https://finance.vietstock.vn/data/corporateaz",
                    data=payload,
                    timeout=15
                )
                
                if response.status_code != 200:
                    continue
                    
                data = response.json()
                
                if not isinstance(data, list) or len(data) == 0:
                    continue 
                
                page_codes = [str(item.get("Code", "")).upper().strip() for item in data]
                valid_codes = [c for c in page_codes if c]
                
                # NẾU BỊ CHẠM NÓC 50 MÃ VÀ TIỀN TỐ CHƯA QUÁ DÀI -> CHẺ NHỎ TIỀN TỐ!
                if len(data) == 50 and len(prefix) < 3:
                    LOG.warning(f" [!] Tiền tố '{prefix}' chạm nóc 50 mã. Phân nhánh chi tiết hơn (VD: {prefix}A, {prefix}B)...")
                    
                    # Tạo ra các nhánh con (VD: BA, BB, BC...)
                    sub_prefixes = [prefix + char for char in string.ascii_uppercase + "0123456789"]
                    
                    # Nạp ngược lại vào đầu hàng đợi để quét ngay lập tức
                    queue = sub_prefixes + queue
                    continue # Bỏ qua kết quả bị cắt xén của chữ B, lát nữa lấy BA, BB... sẽ đầy đủ hơn
                
                all_tickers.extend(valid_codes)
                
                if valid_codes:
                    LOG.info(f" -> [Python] Sàn {cat_id} - Khóa '{prefix}': Thu được {len(valid_codes)} mã.")
                
                time.sleep(0.3)
                
            except Exception as e:
                LOG.error(f"[!] Lỗi phát sinh tại Sàn {cat_id} - Khóa {prefix}: {e}")
                continue

    final_tickers = sorted(list(set(all_tickers)))
    return final_tickers

def main():
    paths = CONFIG.get("paths", {})
    queue_file_path = paths.get("tickers_can_chay_txt", "./ma.txt")
    history_file_path = paths.get("tickers_da_co_txt", "./Du_Lieu_BCTC_Cac_Cong_Ty/tickers_da_co.txt")
    
    # 1. Thu thập toàn bộ danh sách mã từ sàn tài chính
    all_market_tickers = fetch_all_vietstock_tickers_automated()
    
    if not all_market_tickers:
        LOG.error("[-] Tiến trình quét danh sách tự động thất bại hoặc không tìm thấy mã nào.")
        return
        
    LOG.info(f"[✓] Thu thập thành công tổng cộng {len(all_market_tickers)} mã sạch từ Vietstock.")
    
    # 2. Đọc lịch sử các mã đã cào xong để loại trừ
    history_tickers = set()
    if os.path.exists(history_file_path):
        try:
            with open(history_file_path, "r", encoding="utf-8-sig") as h_file:
                content = h_file.read()
                # Tách chuỗi theo dấu phẩy (,), loại bỏ khoảng trắng thừa và ép thành chữ in hoa
                if content.strip():
                    raw_tokens = content.split(",")
                    for token in raw_tokens:
                        clean_ticker = token.strip().upper()
                        if clean_ticker: # Bỏ qua các phần tử rỗng do dấu phẩy thừa
                            history_tickers.add(clean_ticker)
            LOG.info(f"[*] Màng lọc lịch sử: Đã phát hiện và bóc tách thành công {len(history_tickers)} mã đã tồn tại.")
        except Exception as e:
            LOG.warning(f"[!] Không thể đọc file lịch sử: {e}. Tiến hành bỏ qua màng lọc.")

    # 3. Lọc lấy các mã mới chưa chạy
    new_queue_tickers = [ticker for ticker in all_market_tickers if ticker not in history_tickers]
    LOG.info(f"[➔] Màng lọc lịch sử: Loại bỏ các mã trùng. Còn lại {len(new_queue_tickers)} mã mới đưa vào hàng đợi.")
    
    # 4. Ghi thông tin mới vào file hàng đợi chạy
    try:
        # Đảm bảo thư mục cha của file đầu ra tồn tại
        dirname = os.path.dirname(queue_file_path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
            
        with open(queue_file_path, "w", encoding="utf-8") as q_file:
            for ticker in new_queue_tickers:
                q_file.write(f"{ticker}\n")
        LOG.info(f"[✓] Đã cập nhật file hàng đợi thành công tại: {queue_file_path}")
    except Exception as e:
        LOG.error(f"[-] Không thể ghi file hàng đợi mã: {e}")

if __name__ == "__main__":
    main()