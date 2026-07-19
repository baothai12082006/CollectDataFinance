import json
from pathlib import Path

CONFIG_PATH = Path("./config.json")

def load_global_config(config_path: Path = CONFIG_PATH) -> dict:
    if not config_path.exists():
        return {
            "paths": {
                "root_dir": "./Du_Lieu_BCTC_Cac_Cong_Ty",
                "drive_target_dir": "./Du_Lieu_BCTC_Cac_Cong_Ty",
                "excel_path": "/content/drive/MyDrive/DanhMucTaiLieu.xlsx",
                "tickers_da_co_json": "./Du_Lieu_BCTC_Cac_Cong_Ty/tickers_da_co.json",
                "tickers_da_co_txt": "./Du_Lieu_BCTC_Cac_Cong_Ty/tickers_da_co.txt",
                "tickers_can_chay_txt": "./ma.txt",
                "successful_download_log": "./Du_Lieu_BCTC_Cac_Cong_Ty/successful_downloads.jsonl"
            },
            "excel_settings": {
                "sheet_name": "DanhMucTaiLieu", 
                "column_name": "Mã Chứng Khoán",
            },
            "crawler_settings": {
                "collector_name": "Nguyễn Trần Bảo Thái", 
                "years": ["2021", "2022", "2023", "2024", "2025"], 
                "request_workers": 6, 
                "max_retry_rounds": 3
            }
        }
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        # Fallback phòng trường hợp file json bị ghi đè lỗi/trống lúc runtime
        print("[!] File config.json bị lỗi định dạng. Đang dùng cấu hình mặc định.")
        return load_global_config(Path("non_existent_file.json"))

# Khởi tạo instance duy nhất để các file khác import
CONFIG = load_global_config()