# Checklist bảo mật – EventHub

Tài liệu này dùng để rà soát trước khi đưa website lên môi trường thật. Các mục
đánh dấu **[x]** đã được cấu hình trong mã nguồn; **[ ]** là việc cần làm thêm
tùy môi trường triển khai.

## 1. Bí mật và cấu hình

- [x] Không commit `.env`; `.gitignore` chặn `.env`, khóa, chứng chỉ và dữ liệu runtime.
- [x] `.env.example` chỉ chứa giá trị mẫu, không chứa bí mật thật.
- [x] `DJANGO_DEBUG=False` được ép trong `docker-compose.yml`.
- [x] Django từ chối khởi động production nếu `DJANGO_SECRET_KEY` còn là giá trị mẫu hoặc ngắn hơn 32 ký tự.
- [x] Mật khẩu PostgreSQL/pgAdmin/Grafana lấy từ biến môi trường.
- [ ] Thay toàn bộ giá trị mẫu trước khi chạy thật.
- [ ] Dùng secret manager của nhà cung cấp (Vault, AWS Secrets Manager, GitHub Environment secrets…) thay vì file `.env` trên máy chủ dùng chung.
- [ ] Giới hạn quyền đọc `.env` (ví dụ `chmod 600 .env`, chỉ user triển khai đọc được).
- [ ] Luân phiên khóa/mật khẩu định kỳ và ngay khi có người rời nhóm.

## 2. Mạng và cổng

- [x] PostgreSQL không publish cổng ra host; chỉ truy cập trong Docker network `backend`.
- [x] pgAdmin, Prometheus, Grafana, Loki bind `127.0.0.1`, không lộ ra Internet.
- [x] Chỉ Nginx publish cổng HTTP của website (mặc định `8080`).
- [x] Nginx chặn `/metrics` từ bên ngoài; Prometheus scrape trực tiếp `web:8000`.
- [x] `backend` và `monitoring` là Docker network `internal`.
- [ ] Trên server thật, dùng firewall chỉ mở 80/443 (hoặc cổng reverse proxy) và SSH.
- [ ] Truy cập Grafana/Prometheus/pgAdmin qua SSH tunnel hoặc VPN, không mở trực tiếp.
- [ ] Cân nhắc đặt Nginx sau một lớp CDN/WAF nếu website công khai.

## 3. Xác thực và phân quyền

- [x] Mật khẩu được băm bởi Django; không lưu hoặc ghi log mật khẩu.
- [x] Password validators: tối thiểu 8 ký tự, chống mật khẩu phổ biến/toàn số, kiểm tra giống thông tin tài khoản.
- [x] Dashboard quản trị yêu cầu `is_staff`; kiểm tra lại ở từng view.
- [x] Hủy đăng ký của người khác chỉ dành cho staff; tham số `by_staff=True` không đủ nếu tài khoản không phải staff.
- [x] Check-in vé yêu cầu staff.
- [x] CSRF token có trong mọi form POST; cookie CSRF `HttpOnly` + `SameSite=Lax`.
- [x] Session cookie `HttpOnly`, `SameSite=Lax`, thời hạn mặc định 8 giờ.
- [ ] Bật `DJANGO_SECURE_COOKIES=True` khi chạy HTTPS thật.
- [ ] Cân nhắc giới hạn IP truy cập `/django-admin/` hoặc tắt Django admin nếu không dùng.
- [ ] Thêm MFA cho tài khoản quản trị nếu triển khai lâu dài.

## 4. Chống lạm dụng và tấn công web

- [x] Nginx rate limit chung 10 request/giây/IP; endpoint đăng nhập/đăng ký chặt hơn.
- [x] Giới hạn kích thước body 2 MB; Django giới hạn dữ liệu POST 2 MB và 500 trường.
- [x] `server_tokens off`; ẩn phiên bản Nginx.
- [x] Security headers: CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`.
- [x] CSP mặc định không cho inline script/style; chỉ nới cho `/django-admin/` vì admin của Django cần.
- [x] Template Django autoescape; không dùng `|safe` cho dữ liệu người dùng.
- [x] Truy vấn qua ORM, tham số hóa; không nối chuỗi SQL từ input.
- [x] Upload file không được bật; giảm bề mặt tấn công.
- [ ] Bật HTTPS + HSTS trước khi công khai.
- [ ] Cân nhắc CAPTCHA hoặc xác thực email cho đăng ký công khai.
- [ ] Rate limit hiện theo IP và lưu trong bộ nhớ Nginx; nếu chạy nhiều Nginx cần giải pháp phân tán.

## 5. Toàn vẹn nghiệp vụ

- [x] Khóa dòng sự kiện bằng `select_for_update()` khi đăng ký/hủy để chống bán vượt sức chứa.
- [x] Ràng buộc DB: `tickets_sold <= capacity`, `tickets_sold >= 0`, capacity > 0, thời gian hợp lệ.
- [x] Unique `(user, event)` chống đăng ký trùng; unique mã vé UUID.
- [x] Transaction bao trùm tạo registration + ticket + cập nhật `tickets_sold`.
- [x] Không thể đăng ký ngoài cửa sổ đăng ký, sự kiện nháp/đã hủy/hết vé/đã kết thúc.
- [x] Không thể hủy sau khi sự kiện bắt đầu.
- [x] Xóa sự kiện đã có đăng ký bị chặn (`ProtectedError`).
- [x] Test race condition chống oversell chạy trên PostgreSQL (CI).

## 6. Container và máy chủ

- [x] Image được ghim phiên bản cụ thể, không dùng `latest`.
- [x] Container web chạy user UID/GID 10001, không phải root.
- [x] `read_only: true`, `tmpfs` cho `/tmp`, `no-new-privileges:true`.
- [x] Healthcheck cho db, web, nginx, pgAdmin, Prometheus, Grafana. Loki dùng image distroless (không shell/wget) nên không có healthcheck; kiểm tra qua `/ready` hoặc Grafana.
- [x] Volume có tên cho dữ liệu quan trọng (PostgreSQL, static, media, Grafana, Loki…).
- [x] Log container xoay vòng 10 MB × 3 file.
- [ ] Quét lỗ hổng image định kỳ (Trivy, Docker Scout) và cập nhật base image.
- [ ] Giới hạn tài nguyên CPU/RAM (`deploy.resources`) theo tải thực tế.
- [ ] Alloy cần quyền đọc Docker socket – chỉ chấp nhận trên máy chủ tin cậy; nếu không, dùng driver log khác.
- [ ] Bật audit log/monitoring cho máy chủ và Docker daemon.

## 7. Ghi log và dữ liệu cá nhân

- [x] Nginx chỉ ghi JSON với `$uri` (không có query string), method, status, thời gian xử lý.
- [x] Gunicorn access log chỉ ghi method + path (`%(U)s`), không có query string.
- [x] Django JSON log chỉ ghi các trường trong whitelist: ID, quantity, status, method, path, duration…
- [x] Không log mật khẩu, token, session, cookie, email, số điện thoại hay nội dung form. IP được giữ trong access log để vận hành; ẩn/hash nếu chính sách yêu cầu.
- [x] Nội dung lỗi được ghi qua `logger`, không trả stack trace cho người dùng khi DEBUG=False.
- [ ] Đặt thời hạn lưu log phù hợp quy định (Loki đang để 30 ngày).
- [ ] Phân quyền truy cập Loki/Grafana; hiện chỉ bind localhost.
- [ ] Có quy trình xóa dữ liệu người dùng khi được yêu cầu.

## 8. Sao lưu và khôi phục

- [ ] Sao lưu PostgreSQL tự động hằng ngày, mã hóa và lưu ngoài máy chủ.
- [ ] Thử khôi phục định kỳ, không chỉ kiểm tra file backup tồn tại.
- [ ] Sao lưu cấu hình `.env`/secret ở nơi an toàn riêng.
- [ ] Ghi lại RPO/RTO mong muốn.

## 9. Kiểm tra trước khi go-live

```bash
# Trong thư mục dự án
python manage.py check --deploy
docker compose config -q
docker compose exec web python manage.py check
```

- [ ] Chạy `check --deploy` và xử lý cảnh báo.
- [ ] Kiểm tra HTTPS, redirect HTTP → HTTPS, HSTS.
- [ ] Kiểm tra `/metrics` trả 404 qua Nginx.
- [ ] Kiểm tra đăng nhập sai bị rate limit (429) khi gửi liên tục.
- [ ] Kiểm tra không có thông tin nhạy cảm trong log Nginx/Django/Loki.
- [ ] Thử đăng ký đồng thời nhiều tài khoản cho sự kiện sắp hết vé.
- [ ] Kiểm tra sao lưu/khôi phục trên môi trường staging.
