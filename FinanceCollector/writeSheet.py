from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any

import gspread
from google.auth import default
from config import CONFIG


SHEET_NAME = CONFIG["excel_settings"]["sheet_name"]
COLLECTOR_NAME = CONFIG["crawler_settings"]["collector_name"]
SPREADSHEET_ID = CONFIG["excel_settings"]["spreadsheet_id"]
LOG_PATH = Path(CONFIG["paths"]["successful_download_log"])

HEADERS = (
    "Mã Chứng Khoán",
    "Tên Công ty",
    "Năm Báo Cáo",
    "Loại Báo Cáo",
    "Người Thu Thập",
    "Ghi Chú",
)

def _text(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value or "").strip()

def _normalize_name(name: str) -> str:
    """Loại bỏ dấu tiếng Việt, khoảng trắng thừa và chuyển thành chữ thường để so sánh."""
    name = str(name or "").strip().lower()
    return unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')

def load_success_log(log_path: Path) -> list[list[Any]]:
    rows: list[list[Any]] = []
    if not log_path.exists():
        return rows
    for line_number, line in enumerate(log_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip(): continue
        item = json.loads(line)
        missing = [header for header in HEADERS if header not in item]
        if missing:
            raise ValueError(f"Log row {line_number} is missing columns: {missing}")
        rows.append([item.get(header, "") for header in HEADERS])
    return rows

def _new_cell(value: Any) -> dict[str, Any]:
    if isinstance(value, bool): return {"userEnteredValue": {"boolValue": value}}
    if isinstance(value, (int, float)): return {"userEnteredValue": {"numberValue": value}}
    return {"userEnteredValue": {"stringValue": str(value)}}

def write_log_below_last_collector(
    spreadsheet_id: str,
    log_path: Path,
    *,
    collector_name: str = COLLECTOR_NAME,
    clear_log_after_commit: bool = True,
) -> int:
    pending_rows = load_success_log(log_path)
    if not pending_rows:
        return 0

    creds, _ = default()
    client = gspread.authorize(creds)
    worksheet = client.open_by_key(spreadsheet_id).worksheet(SHEET_NAME)

    existing_rows = worksheet.get("A2:F")
    ticker_owner = {}
    company_owner = {}

    for row in existing_rows:
        if len(row) >= 5:
            ticker = _text(row[0])
            company = _text(row[1])
            collector = _text(row[4])

            if ticker:
                ticker_owner[ticker] = collector

            if company:
                company_owner[_normalize_name(company)] = collector
    existing_keys = {tuple(_text(value) for value in row[:6]) for row in existing_rows}

    rows_to_insert = []
    for row in pending_rows:
        ticker = _text(row[0])
        company = _text(row[1])
        collector = _text(row[4])
        # Check mã chứng khoán
        if ticker in ticker_owner:
            if ticker_owner[ticker] != collector:
                print(
                    f"[BLOCK] Mã {ticker} đã thuộc người thu thập "
                    f"{ticker_owner[ticker]}, không cho phép {collector}"
                )
                continue
        # Check tên công ty
        company_key = _normalize_name(company)
        if company_key in company_owner:
            if company_owner[company_key] != collector:
                print(
                    f"[BLOCK] Công ty {company} đã thuộc người thu thập "
                    f"{company_owner[company_key]}, không cho phép {collector}"
                )
                continue

        # Check duplicate toàn dòng cũ (GIỮ NGUYÊN LOGIC CŨ)
        if tuple(_text(value) for value in row) not in existing_keys:
            rows_to_insert.append(row)
    if not rows_to_insert:
        if clear_log_after_commit:
            log_path.write_text("", encoding="utf-8")
        return 0

    # Cơ chế tìm tên thông minh mới
    normalized_collector = _normalize_name(collector_name)
    collector_rows = [
        index + 2 for index, row in enumerate(existing_rows)
        if len(row) >= 5 and _normalize_name(row[4]) == normalized_collector
    ]

    if not collector_rows:
        last_collector_row = len(existing_rows) + 1
    else:
        last_collector_row = max(collector_rows)

    insert_at = last_collector_row + 1
    row_count = len(rows_to_insert)

    requests = [
        {"insertDimension": {"range": {"sheetId": worksheet.id, "dimension": "ROWS", "startIndex": insert_at - 1, "endIndex": insert_at - 1 + row_count}, "inheritFromBefore": True}},
        {"copyPaste": {"source": {"sheetId": worksheet.id, "startRowIndex": last_collector_row - 1, "endRowIndex": last_collector_row, "startColumnIndex": 0, "endColumnIndex": 6}, "destination": {"sheetId": worksheet.id, "startRowIndex": insert_at - 1, "endRowIndex": insert_at - 1 + row_count, "startColumnIndex": 0, "endColumnIndex": 6}, "pasteType": "PASTE_FORMAT", "pasteOrientation": "NORMAL"}},
        {"updateCells": {"start": {"sheetId": worksheet.id, "rowIndex": insert_at - 1, "columnIndex": 0}, "rows": [{"values": [_new_cell(value) for value in row]} for row in rows_to_insert], "fields": "userEnteredValue"}}
    ]

    worksheet.spreadsheet.batch_update({"requests": requests})
    if clear_log_after_commit:
        log_path.write_text("", encoding="utf-8")

    return row_count

# --- ĐOẠN CODE THỰC THI ---


print("[*] Đang tìm kiếm tên và đẩy dữ liệu lên Google Sheets...")
try:
    inserted_rows = write_log_below_last_collector(
        spreadsheet_id=SPREADSHEET_ID,
        log_path=LOG_PATH
    )
    if inserted_rows > 0:
        print(f"[+] Hoàn tất! Đã chèn {inserted_rows} dòng báo cáo mới ngay dưới dòng cũ của bạn.")
    else:
        print("[!] Không có dữ liệu mới nào được thêm vào (Có thể log rỗng hoặc dữ liệu đã bị trùng).")
except Exception as e:
    print(f"[-] Đã xảy ra lỗi khi ghi dữ liệu: {e}")