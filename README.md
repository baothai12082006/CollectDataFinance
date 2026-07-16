# 📊 Trình Tự Động Tải Báo Cáo Tài Chính từ CafeF (Phiên bản V2)

[![Colab](https://img.shields.io/badge/Run%20in-Colab-orange?logo=googlecolab&style=flat-square)](https://colab.research.google.com/)
[![Selenium](https://img.shields.io/badge/Powered%20by-Selenium-green?logo=selenium&style=flat-square)](https://www.selenium.dev/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)

Công cụ tự động hóa mạnh mẽ giúp tải toàn bộ Báo cáo tài chính (BCTC) định kỳ (theo năm và quý) của các doanh nghiệp từ **CafeF**. Chương trình kết hợp hiệu năng của luồng tải bất động bộ (`requests`) và độ tin cậy vượt trội của trình duyệt giả lập (**Selenium Headless**) để vượt qua các cơ chế chặn tải nâng cao.

---

## 🛠️ Hướng Dẫn Cấu Hình Tham Số (Tùy Chỉnh Theo Nhu Cầu)

Để tùy biến công cụ này, bạn hãy mở file code và tìm đến mục **`Configuration`** (khoảng dòng 34-45). Dưới đây là giải thích chi tiết từng thông số bạn có thể chỉnh sửa:

| Tên biến cấu hình | Giá trị mặc định | Giải thích chi tiết & Cách tùy chỉnh |
| :--- | :--- | :--- |
| **`BANK_TICKERS`** | `["CAN", "PPP"]` | **Danh sách mã chứng khoán** cần tải. Bạn có thể thêm bất kỳ mã nào (Ví dụ: `["VCB", "ACB", "HPG", "FPT"]`). Không giới hạn số lượng. |
| **`YEARS`** | `("2021", "2022", "2023", "2024", "2025")` | **Các năm cần lấy báo cáo**. Hệ thống sẽ tự động lọc bỏ các báo cáo thuộc các năm không nằm trong bộ lọc này. |
| **`COLLECTOR_NAME`** | `"Nguyễn Trần Bảo Thái"` | **Tên người thu thập**. Tên này sẽ được ghi trực tiếp vào cột *"Người Thu Thập"* trong file log kết quả (`successful_downloads.jsonl`) để phục vụ báo cáo. |
| **`ROOT_DIR`** | `Path("./Du_Lieu_BCTC_Cac_Cong_Ty")` | Thư mục lưu trữ tạm thời trên bộ nhớ đệm của Google Colab. Thông thường không cần thay đổi. |
| **`DRIVE_TARGET_DIR`** | `Path("/content/drive/MyDrive/...")` | **Thư mục đích trên Google Drive** của bạn. Bạn có thể đổi tên thư mục này để lưu vào các vị trí khác nhau trên Drive cá nhân. |
| **`MIN_FILE_BYTES`** | `10 * 1024` (10 KB) | **Kích thước file tối thiểu**. Bất kỳ tệp nào tải về nhỏ hơn 10KB sẽ bị coi là lỗi (thường là trang HTML thông báo lỗi "403 Forbidden" hoặc "Page Not Found") và sẽ được đưa vào hàng đợi để tải lại. |
| **`REQUEST_WORKERS`** | `6` | **Số luồng tải đồng thời** khi sử dụng `requests`. <br>• *Tăng lên (10-12):* Tốc độ tải cực nhanh nhưng dễ bị CafeF chặn IP tạm thời.<br>• *Giảm xuống (2-4):* Tải chậm hơn nhưng an toàn, ít bị quét lỗi. |
| **`MAX_RETRY_ROUNDS`** | `3` | **Số vòng thử lại bằng Selenium**. Nếu tải đa luồng thất bại, trình duyệt Chrome ẩn sẽ khởi chạy và thử lại tối đa 3 lần với nhiều chiến lược click chuột khác nhau. |
| **`PAGE_WAIT_SECONDS`** | `15` | Thời gian tối đa (giây) chờ trang web CafeF tải xong trước khi báo lỗi Timeout. Tăng lên nếu mạng của bạn bị chậm/chập chờn. |
| **`DOWNLOAD_WAIT_SECONDS`** | `20` | Thời gian tối đa (giây) chờ trình duyệt tải trọn vẹn tệp PDF về máy trước khi chuyển sang tác vụ khác. Hãy tăng lên nếu tệp báo cáo quá nặng (>50MB). |

---

## 🚀 Cách Hoạt Động Của Pipeline Tải File

Hệ thống hoạt động tự động khép kín qua 4 giai đoạn chính:

```text
  [1. Quét tìm Link] ───> [2. Tải nhanh đa luồng] ───> [3. Quản lý lỗi & Selenium] ───> [4. Đồng bộ hóa]
  (Quét trang CafeF,     (Sử dụng thư viện requests,     (Các file lỗi/bị chặn sẽ được     (Đồng bộ lên Drive,
   phân loại năm/quý)     tải 6 file cùng lúc)            Chrome giả lập click để cứu vãn)   xuất log Excel/JSON)
