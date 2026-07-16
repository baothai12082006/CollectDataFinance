# 📊 Trình Tự Động Tải Báo Cáo Tài Chính từ CafeF (Phiên bản V2)

[![Colab](https://img.shields.io/badge/Run%20in-Colab-orange?logo=googlecolab&style=flat-square)](https://colab.research.google.com/)
[![Selenium](https://img.shields.io/badge/Powered%20by-Selenium-green?logo=selenium&style=flat-square)](https://www.selenium.dev/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)

Công cụ tự động hóa mạnh mẽ giúp tải toàn bộ Báo cáo tài chính (BCTC) định kỳ (theo năm và quý) của các doanh nghiệp từ **CafeF**. Chương trình kết hợp hiệu năng của luồng tải bất đồng bộ (`requests`) và độ tin cậy vượt trội của trình duyệt giả lập (**Selenium Headless**) để vượt qua các cơ chế chặn tải nâng cao.

---

## ✨ Tính Năng Nổi Bật

*   **Tải Đa Luồng Siêu Tốc (Requests-session):** Thử nghiệm tải nhanh bằng Requests với cơ chế tự động thử lại (Retry) và Pool kết nối trước để tiết kiệm thời gian.
*   **Cơ Chế Dự Phòng Thông Minh (Selenium Fallback):** Nếu tải bằng API/Link trực tiếp thất bại, hệ thống tự động khởi động Google Chrome ngầm để thực hiện click giả lập (hỗ trợ nhiều hành động click khác nhau) và bóc tách cookie.
*   **Chuẩn Hóa Thư Mục Đầu Ra:** 
    *   Tự động bóc tách và viết tắt các danh từ chung trong tên công ty (ví dụ: `Tổng công ty` -> `TCT`, `Cổ phần` -> `CP`).
    *   Sử dụng định dạng thư mục phân cấp khoa học: `Tên_Công_Ty/Năm/Quý` (hoặc `Tên_Công_Ty/Năm` đối với báo cáo cả năm).
*   **Tích Hợp Google Drive:** Tự động đồng bộ hóa dữ liệu tải về sang tài khoản Drive của bạn một cách an toàn.
*   **Quản Lý Trạng Thái Thông Minh:** Lưu bộ nhớ đệm (`tasks.json`) giúp bạn có thể tiếp tục tải tiếp từ vị trí bị gián đoạn mà không cần quét lại từ đầu.
*   **Báo Cáo Chi Tiết:** Kết xuất 2 file nhật ký định dạng JSONLines (`successful_downloads.jsonl` và `companies_failed.jsonl`) để theo dõi tiến độ dễ dàng.

---

## 🛠️ Yêu Cầu Hệ Thống & Cài Đặt

Mã nguồn được tối ưu hóa để chạy trực tiếp trên môi trường **Google Colab (Ubuntu Linux)**. Để khởi chạy thành công, công cụ sẽ tự động cài đặt các thành phần sau ở những dòng code đầu tiên:

1.  **Google Chrome Stable** (Trình duyệt chính thức)
2.  **Selenium WebDriver** (Thư viện điều khiển trình duyệt)
3.  **pypdf & Requests** (Xử lý tệp tin và luồng mạng)

---

## 🚀 Hướng Dẫn Sử Dụng Trên Google Colab

### Bước 1: Chuẩn bị tệp chạy
1. Tải file `.ipynb` này lên Google Drive của bạn.
2. Mở file bằng ứng dụng **Google Colaboratory**.

### Bước 2: Tùy chỉnh danh sách doanh nghiệp cần tải
Tìm đến đoạn cấu hình (`Configuration`) trong file code và chỉnh sửa các tham số tùy theo nhu cầu của bạn:

```python
# Danh sách mã chứng khoán bạn muốn thu thập dữ liệu
BANK_TICKERS = ["CAN", "PPP"]  

# Các năm cần lấy báo cáo
YEARS = ("2021", "2022", "2023", "2024", "2025")

# Tên người thực hiện (sẽ ghi vào file log thành công)
COLLECTOR_NAME = "Nguyễn Trần Bảo Thái"
