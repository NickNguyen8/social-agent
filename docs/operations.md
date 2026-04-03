# Vận hành

---

## Khởi động

```bash
cd social-agent

# Kiểm tra trước khi chạy
python cli.py validate

# Chạy scheduler daemon
python cli.py run
```

Scheduler đọc lịch từ `config.yaml` → đăng bài theo cron của từng target.  
Nhấn **Ctrl+C** để dừng.

---

## Quy trình hàng ngày

### Tự động hoàn toàn (`review_mode: false`)

```
Scheduler chạy nền → đăng bài → ghi audit log
Bạn: kiểm tra stats cuối ngày nếu muốn
```

### Có review (`review_mode: true`)

```
Scheduler chạy → lưu queue
Bạn: xem queue → approve/reject
Bài approved → đăng ngay
```

```bash
# Xem bài chờ duyệt (chạy buổi sáng)
python cli.py review

# Approve bài nào thấy OK
python cli.py review --approve ID

# Reject bài nào không phù hợp
python cli.py review --reject ID
```

---

## Monitoring

### Xem thống kê

```bash
python cli.py stats           # 20 bài gần nhất
python cli.py stats --limit 50
```

### Xem log trực tiếp

```bash
tail -f logs/app.log
```

### Audit log (raw)

```bash
# Xem 10 bài cuối
tail -n 10 logs/posts.jsonl | python3 -m json.tool

# Chỉ bài thất bại
grep '"success": false' logs/posts.jsonl
```

---

## Xử lý lỗi thường gặp

### Token hết hạn / 403

```
Error: HTTP 403 / OAuthException
```

→ Renew token: xem [tokens.md](tokens.md)  
→ Sau khi renew: `python cli.py validate`

### Rate limit Facebook (429 / error code 4, 17)

Agent tự retry với exponential backoff (2s → 4s → 8s).  
Nếu vẫn fail: đợi 1 giờ trước khi chạy lại.

Graph API limit: 200 calls/hour/user.

### JSON truncation từ LLM

```
JSONDecodeError: Expecting value
```

→ Kiểm tra `config.yaml` → `llm.max_tokens` ≥ 4096  
→ Agent tự retry 3 lần với backoff

### Facebook Checkpoint (Personal Profile)

```
ProfileCheckpointError: Facebook requires verification
```

→ Mở Chrome với profile đó → vào facebook.com → hoàn thành xác minh thủ công  
→ Đừng đăng xuất → chạy lại agent

### Gemini 429 (quota)

Free tier: 15 req/min. Nếu schedule nhiều target quá gần nhau:  
→ Giãn cron schedule ra (ví dụ `0 8 * * *` thay vì `0 8,9,10 * * *`)  
→ Hoặc upgrade Gemini API Paid tier

### Research fetch thất bại

Agent ghi `sources_failed` nhưng vẫn generate bài (dùng `topic.description` làm fallback).  
Kiểm tra log để biết nguồn nào bị lỗi:

```bash
grep "ResearchAgent" logs/app.log | tail -20
```

---

## Thêm target mới (checklist)

- [ ] Lấy token (xem [tokens.md](tokens.md))
- [ ] Thêm env var vào `.env`
- [ ] Thêm target vào `config.yaml`
- [ ] `python cli.py validate` — kiểm tra kết nối
- [ ] `python cli.py post -t NEW_ID --dry-run` — test generate
- [ ] Bật `enabled: true`
- [ ] Cân nhắc `review_mode: true` cho giai đoạn đầu

---

## Backup & Recovery

```bash
# Backup audit log và review queue
cp logs/posts.jsonl logs/posts.jsonl.bak
cp logs/review_queue.jsonl logs/review_queue.jsonl.bak
```

Log xoay vòng tự động: `app.log` tối đa 10MB × 5 files = 50MB.

---

## Tắt 1 target tạm thời

```yaml
# config.yaml
targets:
  - id: fastdx_page
    enabled: false   # ← tắt, không cần xóa cron
```

Restart scheduler để áp dụng: Ctrl+C → `python cli.py run`
