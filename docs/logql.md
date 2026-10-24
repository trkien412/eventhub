# Truy vấn log với Loki và LogQL

## 1. Luồng log

```
Django/Gunicorn stdout ─┐
Nginx access/error log ─┼─> Grafana Alloy (Docker socket) ─> Loki ─> Grafana Explore
PostgreSQL, Loki...    ─┘
```

- Alloy chỉ thu log của container có tên bắt đầu bằng `event-` (xem
  `monitoring/alloy/config.alloy`).
- Nhãn (label) do Alloy gắn: `container`, `stream`, `job="docker"`,
  `env="production"`, `cluster="eventhub"`.
- Log Django là JSON; log Nginx access cũng là JSON. Dùng parser `| json` để
  truy vấn từng trường.
- Loki giữ log 30 ngày (`retention_period: 720h`) và từ chối mẫu cũ hơn 7 ngày
  (`reject_old_samples_max_age: 168h`).
- Không có mật khẩu, token, session hay query string trong log; không ghi
  email/tên/số điện thoại. Địa chỉ IP vẫn có trong access log để vận hành và
  điều tra sự cố. Vì vậy không thể tìm theo username/email; hãy dùng ID
  (`actor_id`, `event_id`…).

## 2. Mở Grafana Explore

1. Mở http://127.0.0.1:3000 (chỉ trên máy chủ hoặc qua SSH tunnel).
2. Đăng nhập bằng tài khoản trong `.env` (`GF_SECURITY_ADMIN_*`).
3. Chọn **Explore** → datasource **Loki**.
4. Dán truy vấn, chọn khoảng thời gian, bấm **Run query**.

Có thể gọi API trực tiếp (Loki chỉ bind localhost):

```bash
curl -G -s "http://127.0.0.1:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={container="event-web"} | json | level="ERROR"' \
  --data-urlencode 'limit=50'
```

## 3. Truy vấn mẫu

### 3.1. Log ứng dụng

Tất cả log của container web:

```logql
{container="event-web"}
```

Chỉ log lỗi:

```logql
{container="event-web"} | json | level="ERROR"
```

Đăng ký vé thành công (audit nghiệp vụ):

```logql
{container="event-web"} | json | message="ticket_registration_created"
```

Đăng ký bị từ chối do dữ liệu thay đổi đồng thời:

```logql
{container="event-web"} | json | message="ticket_registration_rejected"
```

Check-in vé:

```logql
{container="event-web"} | json | message="ticket_checked_in"
```

Lọc theo sự kiện hoặc người dùng (dùng ID, không dùng PII):

```logql
{container="event-web"} | json | event_id=1
{container="event-web"} | json | actor_id=3
```

Hiển thị thông điệp gọn hơn:

```logql
{container="event-web"} | json | line_format "{{.level}} {{.message}} event={{.event_id}}"
```

Đếm log theo mức độ trong 5 phút:

```logql
sum by (level) (count_over_time({container="event-web"} | json [5m]))
```

### 3.2. Log Nginx

Tất cả request:

```logql
{container="event-nginx"} | json
```

Response lỗi 5xx:

```logql
{container="event-nginx"} | json | status >= 500
```

Response 4xx:

```logql
{container="event-nginx"} | json | status >= 400 | status < 500
```

Rate limit trên trang đăng nhập:

```logql
{container="event-nginx"} | json | uri="/accounts/login/" | status=429
```

Request chậm hơn 1 giây:

```logql
{container="event-nginx"} | json | request_time > 1
```

Tìm request vào một nhóm đường dẫn:

```logql
{container="event-nginx"} | json | uri=~"/events/.*"
```

Bỏ qua healthcheck:

```logql
{container="event-nginx"} | json | uri!="/healthz"
```

Đếm request theo status trong 5 phút:

```logql
sum by (status) (count_over_time({container="event-nginx"} | json [5m]))
```

Đếm request theo URI (top đường dẫn):

```logql
topk(10, sum by (uri) (count_over_time({container="event-nginx"} | json [1h])))
```

### 3.3. Log toàn bộ stack

Tất cả container EventHub:

```logql
{job="docker"}
```

Container PostgreSQL:

```logql
{container="event-db"} |= "ERROR"
```

Container Loki:

```logql
{container="event-loki"} |= "level=error"
```

> Lưu ý: Alloy thu log của mọi container `event-*`, kể cả Loki, Grafana và
> chính Alloy. Nếu log hạ tầng gây nhiễu khi điều tra ứng dụng, lọc bỏ bằng
> `container!~"event-(loki|grafana|alloy)"`.

## 4. Trường JSON thường dùng

| Nguồn | Trường | Ý nghĩa |
|---|---|---|
| Django | `time`, `level`, `logger`, `message` | Thông tin cơ bản |
| Django | `event_id`, `registration_id`, `ticket_id`, `actor_id` | ID nghiệp vụ (không phải PII) |
| Django | `quantity`, `status_code`, `method`, `path`, `duration_ms` | Ngữ cảnh request |
| Nginx | `time`, `request_id`, `remote_addr` | Thời điểm, mã request, IP |
| Nginx | `method`, `uri`, `status`, `bytes` | Request/response (không có query string) |
| Nginx | `request_time`, `upstream_time` | Ngữ cảnh hiệu năng |

Nginx **không** ghi `referer` và `user_agent` để tránh lộ query string/token
trong referer và giảm khả năng fingerprint người dùng.

## 5. Mẹo debug

- Không thấy log: kiểm tra `docker compose ps`, `docker logs event-alloy`,
  `docker logs event-loki`; đảm bảo container name bắt đầu bằng `event-`.
- Truy vấn quá cũ: Loki từ chối sample cũ hơn 7 ngày; chọn khoảng thời gian gần.
- Không parse được JSON: xem log thô `{container="event-web"}` trước, sau đó mới
  thêm `| json`.
- Log Nginx không có query string là chủ đích bảo mật. Nếu cần điều tra sâu,
  dùng `request_id` để đối chiếu với log ứng dụng (Django nhận header
  `X-Request-ID`).
- Không dùng LogQL để tìm mật khẩu/token; các trường đó không được ghi log.
