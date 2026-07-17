# CafeF Financial Report Downloader & Google Sheets Sync

Một pipeline tự động hóa mạnh mẽ được thiết kế để chạy trên **Google Colab** nhằm thu thập, tải xuống báo cáo tài chính (BCTC) của các công ty niêm yết từ trang tin tài chính CafeF, quản lý lưu trữ trên Google Drive, tự động đồng bộ danh sách mã chứng khoán từ file Excel và cập nhật trạng thái tải xuống trực tiếp lên Google Sheets theo thời gian thực.

---

## 📌 Các Tính Năng Chính
1. **Thu Thập Đa Luồng (Hybrid Crawling):** Kết hợp giữa requests tốc độ cao (ThreadPoolExecutor) để tải trực tiếp và trình duyệt giả lập Headless Chrome (Selenium WebDriver) để vượt qua các lớp bảo vệ/bắt buộc click Javascript của CafeF.
2. **Quản Lý Cache & Khôi Phục Lỗi:** Lưu trữ tiến trình trong `tasks.json`. Nếu bị ngắt kết nối (Disconnect Colab), mã nguồn sẽ tự động nhận diện các file đã tải để tiếp tục tiến trình mà không cần tải lại từ đầu.
3. **Quản Lý Mã Chứng Khoán Tích Lũy:** Đọc cột "Mã Chứng Khoán" từ file danh mục dạng Excel trên Google Drive, gộp với danh sách lịch sử trong file JSON/TXT để tích lũy dồn dập, tự động loại bỏ trùng lặp.
4. **Đồng Bộ Google Sheets Thông Minh:** Đẩy kết quả tải thành công lên Google Sheets. Thuật toán tìm kiếm tên thông minh tự động định vị và chèn dòng mới ngay bên dưới khu vực thuộc về người thu thập (`Nguyễn Trần Bảo Thái`), đồng thời sao chép định dạng dòng cũ.

---

## 🛠️ Hướng Dẫn Thiết Lập & Chạy Trên Google Colab

### Bước 1: Chuẩn bị trên Google Drive
Trước khi khởi chạy code, đảm bảo cấu trúc thư mục của bạn trên Google Drive có sẵn các tài nguyên sau:
* File danh mục tài liệu định dạng Excel tại đường dẫn:
  `My Drive/DanhMucTaiLieu.xlsx`
  Trong file này, cần có một sheet mang tên `DanhMucTaiLieu` chứa cột mang tên chính xác là `Mã Chứng Khoán`.
* Id của Google Spreadsheet (nơi chứa sheet danh mục cần cập nhật kết quả). Lấy chuỗi ký tự ID từ URL của bảng tính:
  `https://docs.google.com/spreadsheets/d/📂[ID_SHEET_CUA_BAN]/edit...`

### Bước 2: Tạo Notebook và Mount Drive
Mở Google Colab, tạo một notebook mới (`.ipynb`), dán toàn bộ mã nguồn vào và chạy cell đầu tiên để Mount Google Drive cá nhân:
```python
from google.colab import drive
drive.mount("/content/drive")
```

### Bước 3: Cấu hình biến môi trường và chạy Pipeline
Sau khi Mount thành công, hệ thống sẽ tự động cài đặt Google Chrome Stable cùng các thư viện bổ trợ (`selenium`, `pypdf`, `requests`, `gspread`). Bạn chỉ cần nhấn nút **Run All** và cấp quyền Google Account khi popup xác thực Google Sheets hiển thị.

---

## ⚙️ Hướng Dẫn Thay Đổi Cấu Hình Cho Phù Hợp Nhu Cầu

Để tùy biến công cụ này cho các dự án thu thập dữ liệu khác, bạn có thể chỉnh sửa trực tiếp các tham số cấu hình được định nghĩa trong mã nguồn:

### 1. Thay đổi danh sách mã chứng khoán thu thập trực tiếp
Mặc định trong code đang cấu hình cố định danh sách ngân hàng mẫu là `["PVI"]`. Để mở rộng hoặc thay đổi, hãy sửa biến:
```python
BANK_TICKERS = ["PVI", "TCB", "VCB", "SSI"]  # Thêm các mã chứng khoán bạn cần tải
```

### 2. Thay đổi các năm báo cáo cần lấy
Nếu muốn thu thập các năm cũ hơn hoặc năm tương lai, sửa bộ tuple `YEARS`:
```python
YEARS = ("2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025")
```

### 3. Tối ưu hóa số luồng tải (Tăng tốc độ)
Mặc định hệ thống chạy với 6 luồng tải song song bằng requests. Bạn có thể tăng số luồng này lên nếu kết nối internet trên Colab mạnh mẽ (tuy nhiên không nên đặt quá cao để tránh bị chặn IP):
```python
REQUEST_WORKERS = 10  # Tăng lên 10-12 luồng nếu cần tải cực nhanh
```

### 4. Thay đổi thông tin Người thu thập (Google Sheets)
Khi đẩy kết quả tải lên Google Sheets, hệ thống sẽ chèn tên của bạn vào cột tương ứng. Để đổi tên này, hãy chỉnh sửa hằng số:
```python
COLLECTOR_NAME = "Nguyễn Trần Bảo Thái"  # Thay bằng tên của bạn
```

### 5. Cập nhật ID Google Sheet cá nhân
Hãy thay thế ID của bảng tính Google Sheet của bạn vào hằng số ở phần cuối của code:
```python
SPREADSHEET_ID = "Id_Sheet_Cua_Ban_O_Day"  # Thay bằng chuỗi ID thực tế
```

---

## 📂 Sơ Đồ Cấu Trúc Thư Mục Kết Quả (Sau Khi Chạy)
Sau khi quá trình tải xuống hoàn tất, các báo cáo tài chính sẽ được lưu trữ đồng bộ cả ở Local (Colab) và Google Drive theo cấu trúc chuẩn hóa:

```text
Du_Lieu_BCTC_Cac_Cong_Ty/
├── tickers_da_co.json              # Danh sách mã tích lũy từ Excel (Dạng JSON)
├── tickers_da_co.txt               # Danh sách mã tích lũy từ Excel (Dạng Plain Text)
├── cafef_downloader_v2.log         # Nhật ký hệ thống chi tiết
├── tasks.json                      # Cache lưu danh sách các link/tải dở dang
└── [Mã_Chứng_Khoán]/              # Thư mục riêng của từng công ty (Ví dụ: PVI)
    ├── 2024/
    │   ├── PVI_2024_CN.pdf         # Báo cáo năm
    │   └── PVI_2024_Q2_M.pdf       # Báo cáo Quý 2 (Mẹ)
    └── 2025/
        └── PVI_2025_Q1.pdf         # Báo cáo Quý 1
```

---

## 🛡️ Các Cơ Chế Tự Động Sửa Lỗi Tích Hợp
* **Tự động dọn dẹp file hỏng:** Những file tải về có dung lượng `< 10 KB` hoặc bị trả về mã lỗi HTML từ server CafeF thay vì file PDF thực tế sẽ bị hệ thống tự động xóa và đưa lại vào hàng đợi để tải lại bằng cơ chế Selenium click.
* **Cơ chế ghi đè thông minh:** File đã tải thành công ở các phiên trước và vượt qua bài kiểm tra tính toàn vẹn (integrity check) sẽ được bỏ qua, tiết kiệm băng thông và tài nguyên.
