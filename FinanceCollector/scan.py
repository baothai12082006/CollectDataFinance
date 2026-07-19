from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import pandas as pd
from config import CONFIG
# ------------------------------- Configuration --------------------------------
DEFAULT_EXCEL_PATH = Path(CONFIG["paths"]["excel_path"])
DEFAULT_SHEET_NAME = CONFIG["excel_settings"]["sheet_name"]
DEFAULT_COLUMN_NAME = CONFIG["excel_settings"]["column_name"]
DEFAULT_OUTPUT_JSON = Path(CONFIG["paths"]["tickers_da_co_json"])
DEFAULT_OUTPUT_TXT  = Path(CONFIG["paths"]["tickers_da_co_txt"])

def configure_logger() -> logging.Logger:
    logger = logging.getLogger("scanner")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)
    return logger

LOG = logging.getLogger("scanner")

def extract_tickers_pandas(excel_path: Path, sheet_name: str, column_name: str) -> list[str]:
    LOG.info(f"Đang đọc file Excel: {excel_path} (Sheet: '{sheet_name}') ...")
    
    try:
        df = pd.read_excel(excel_path, sheet_name=sheet_name)
    except Exception as e:
        LOG.error(f"Không thể đọc file Excel hoặc Sheet không tồn tại: {e}")
        return []

    # 1. Tìm cột: Đôi khi header không nằm ở dòng đầu tiên của file Excel
    target_col = None
    for col in df.columns:
        if str(col).strip() == column_name:
            target_col = col
            break

    # Nếu không tìm thấy ở header chính, ta quét tiếp trong 10 hàng dữ liệu đầu tiên
    if target_col is None:
        for idx, row in df.head(10).iterrows():
            for col in df.columns:
                if str(row[col]).strip() == column_name:
                    # Đặt lại tên cột và cắt bỏ phần thừa phía trên
                    df.columns = df.iloc[idx]
                    df = df.iloc[idx + 1:]
                    target_col = column_name
                    break
            if target_col:
                break

    if target_col is None:
        LOG.warning(f"Không tìm thấy cột '{column_name}' trong dữ liệu hiện tại.")
        return []

    # 2. Lấy dữ liệu, chuẩn hóa (viết hoa, xóa khoảng trắng, loại bỏ NaN)
    LOG.info(f"Đang trích xuất mã chứng khoán từ cột '{target_col}'...")
    tickers_series = df[target_col].dropna().astype(str)

    tickers = set()
    for val in tickers_series:
        cleaned = val.strip().upper()
        if cleaned and cleaned != "NAN":  # Loại bỏ các giá trị rỗng/lỗi chuỗi
            tickers.add(cleaned)

    return sorted(list(tickers))

def save_results(tickers: list[str], json_path: Path, txt_path: Path) -> None:
    # Đảm bảo thư mục cha tồn tại
    json_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.parent.mkdir(parents=True, exist_ok=True)

    # Lưu JSON (Phục vụ việc đọc tích lũy lịch sử cho scan.py)
    json_path.write_text(json.dumps(tickers, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # Lưu TXT (Định dạng phân tách bằng dấu phẩy để nạp thẳng vào crawler.py)
    txt_content = ",".join(tickers)
    txt_path.write_text(txt_content, encoding="utf-8")
    
    LOG.info(f"Đã lưu kết quả JSON tại: {json_path}")
    LOG.info(f"Đã lưu kết quả TXT (dạng chuỗi phân tách bằng dấu phẩy) tại: {txt_path}")

def main() -> None:
    parser = argparse.ArgumentParser(description="Excel Ticker Scanner & Aggregator")
    parser.add_argument("--excel_path", type=str, default=str(DEFAULT_EXCEL_PATH), help="Đường dẫn file Excel danh mục")
    parser.add_argument("--sheet", type=str, default=DEFAULT_SHEET_NAME, help="Tên sheet chứa dữ liệu")
    parser.add_argument("--column", type=str, default=DEFAULT_COLUMN_NAME, help="Tên cột mã chứng khoán")
    parser.add_argument("--output_json", type=str, default=str(DEFAULT_OUTPUT_JSON), help="Đường dẫn lưu file JSON")
    parser.add_argument("--output_txt", type=str, default=str(DEFAULT_OUTPUT_TXT), help="Đường dẫn lưu file TXT")
    
    args = parser.parse_args()
    configure_logger()

    excel_path = Path(args.excel_path)
    output_json = Path(args.output_json)
    output_txt = Path(args.output_txt)

    if not excel_path.exists():
        LOG.error(f"Lỗi: Không tìm thấy file Excel tại '{excel_path}'.")
        return

    # 1. Đọc danh sách mã mới từ file Excel hiện tại
    excel_tickers = extract_tickers_pandas(excel_path, args.sheet, args.column)
    LOG.info(f"Tìm thấy {len(excel_tickers)} mã trong file Excel hiện tại.")

    # 2. Đọc danh sách mã đã tích lũy từ trước trong file JSON (nếu có)
    existing_tickers = set()
    if output_json.exists():
        try:
            old_data = json.loads(output_json.read_text(encoding="utf-8"))
            existing_tickers = set(str(t).strip().upper() for t in old_data)
            LOG.info(f"Đã đọc {len(existing_tickers)} mã lịch sử từ file JSON cũ.")
        except Exception:
            LOG.warning("File JSON cũ bị lỗi hoặc trống. Sẽ khởi tạo mới.")

    # 3. Gộp hai danh sách lại với nhau (tự động loại bỏ trùng lặp)
    final_tickers = sorted(list(existing_tickers.union(excel_tickers)))

    # 4. Lưu lại kết quả cuối cùng
    LOG.info(f"Tổng số mã tích lũy sau khi đồng bộ: {len(final_tickers)}")
    save_results(final_tickers, output_json, output_txt)
    LOG.info("Tiến trình quét hoàn tất thành công!")

if __name__ == "__main__":
    main()