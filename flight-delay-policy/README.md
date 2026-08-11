# Bảo hiểm Trễ Chuyến Bay — Atadi.vn × Bảo hiểm PVI

Trang **policy wording** (quy tắc bảo hiểm) cho chương trình Flight Delay Insurance, viết bằng **HTML + CSS + JavaScript thuần** — không dùng framework, dễ chỉnh sửa và đưa vào Google Antigravity.

## 1. Cấu trúc thư mục

```
flight-delay-policy/
├── index.html    # Toàn bộ nội dung & cấu trúc trang
├── styles.css    # Thiết kế hiển thị màn hình (desktop + mobile)
├── print.css     # Tối ưu khi In / xuất PDF khổ A4 (media="print")
├── script.js     # Menu mobile, scroll-spy mục lục, nút In
├── assets/       # Logo PVI, Atadi & mã QR (PNG nền trong suốt)
│   ├── pvi-logo.png
│   ├── atadi-logo.png
│   └── claims-qr.png
└── README.md     # Tài liệu này
```

## 2. Cách chạy

Chỉ cần mở `index.html` bằng trình duyệt (Chrome / Edge / Safari) — không cần server.
Nếu muốn chạy qua server tĩnh (tùy chọn):

```bash
# Python
python3 -m http.server 8080
# hoặc Node
npx serve .
```

Rồi mở `http://localhost:8080`.

## 3. Xuất PDF / In khổ A4

- Bấm nút **“Tải / In bản PDF”** ở Hero, hoặc nhấn `Ctrl/Cmd + P`.
- Trong hộp thoại in: chọn khổ **A4**, bật **Background graphics** (Đồ họa nền) để giữ màu bảng & nhãn.
- File `print.css` tự động: ẩn thanh điều hướng, chuyển khối liên hệ nền tối → nền sáng, chống ngắt trang giữa bảng/thẻ.

## 4. Chỗ cần điền nội dung (đánh dấu sẵn)

Các ô có dạng `[___]` (class `.fill`, viền xanh nét đứt) là **chỗ cần điền / cập nhật** trước khi phát hành:

| Vị trí | Nội dung cần điền |
|---|---|
| Mục **Quy trình yêu cầu bồi thường** → Cổng bồi thường | Cập nhật **mã QR** (`assets/claims-qr.png`) trỏ tới link Cổng bồi thường thực tế |

> Quyền lợi đã cố định: trễ **từ 120 phút liên tục trở lên** → **500.000 VND / chuyến / người** (theo Giấy chứng nhận bảo hiểm). Đơn vị bảo hiểm: **Công ty Bảo hiểm PVI Thủ Đô**. Hotline **(+84) 24 3377 2288 / (84) 969 871 166**, International SOS **(84) 28 3999 8110**, email **atadi.support@pvi.com.vn** đã điền sẵn.

### Bố cục các phần (theo thứ tự)

1. Tóm tắt quyền lợi chính · 2. Đối tượng bảo hiểm · 3. Định nghĩa chính · 4. Điều khoản chung · 5. Quyền lợi bảo hiểm · 6. Loại trừ bảo hiểm · 7. Quy trình yêu cầu bồi thường (gồm Cổng bồi thường + Hồ sơ) · 8. Liên hệ & hỗ trợ.

## 5. Cách chỉnh nội dung

- **Sửa câu chữ:** mở `index.html`, mỗi phần là một `<section class="block" id="...">` có chú thích rõ ràng (ví dụ `<!-- 6. EXCLUSIONS -->`).
- **Thêm/bớt điểm loại trừ hoặc khoản mục:** thêm `<li>...</li>` trong `<ol class="list list--excl">` (số thứ tự tự động).
- **Đổi màu thương hiệu:** sửa biến CSS ở đầu `styles.css` trong khối `:root` (`--blue`, `--ink`, `--paper`...).
- **Đổi font:** thay thẻ `<link>` Google Fonts trong `index.html` và biến `--font-serif` / `--font-sans`.
- **Logo:** đặt trong thư mục `assets/`. Nav hiển thị logo PVI trước rồi Atadi; footer hiển thị cả hai. Thay logo bằng cách ghi đè file `assets/pvi-logo.png` / `assets/atadi-logo.png` (giữ nền trong suốt) hoặc đổi đường dẫn `src` trong `index.html`. Chỉnh chiều cao hiển thị qua các rule `.nav__logo-pvi`, `.nav__logo-atadi`, `.foot__logo-img--*` trong `styles.css`.
- **Nền trời động ở Hero:** điều khiển bằng các rule `.sky`, `.cloud`, `.plane` trong `styles.css`; tự tắt khi thiết bị bật `prefers-reduced-motion` và ẩn khi in.

## 6. Khả năng tương thích

- Responsive: desktop (mục lục dính bên trái) và mobile (menu thu gọn, 1 cột).
- Hoạt động offline, không phụ thuộc CDN ngoài Google Fonts (có thể nhúng font cục bộ nếu cần in offline).

## 7. Lưu ý pháp lý

Trang chỉ trình bày **Quy tắc bảo hiểm** phục vụ tham khảo. Quyền lợi, số tiền bảo hiểm, mức thời gian trễ tối thiểu, phí và điều kiện cụ thể áp dụng theo **Hợp đồng / Giấy chứng nhận bảo hiểm** và **Bảng quyền lợi bảo hiểm** chính thức. Khi có khác biệt, nội dung Hợp đồng / Giấy chứng nhận chính thức là căn cứ áp dụng. Mọi dẫn chiếu về thời gian áp dụng theo **giờ Việt Nam**.
