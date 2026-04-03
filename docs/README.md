# Social Agent — Workspace Docs

Tài liệu nội bộ cho dự án **Social Auto-Post Agent** của FastDX.  
Đây là workspace trung tâm — mọi quyết định, cấu hình, kế hoạch đều được ghi lại ở đây.

---

## Tài liệu

| File | Nội dung |
|------|----------|
| [architecture.md](architecture.md) | Kiến trúc hệ thống, luồng dữ liệu, sơ đồ file |
| [configuration.md](configuration.md) | Toàn bộ options của `config.yaml` giải thích chi tiết |
| [content-strategy.md](content-strategy.md) | Topics, formats, scenarios, brand voice FastDX |
| [research-agent.md](research-agent.md) | Hướng dẫn Research Agent — nguồn cố định & dynamic |
| [tokens.md](tokens.md) | Quản lý token Facebook, LinkedIn, Gemini |
| [operations.md](operations.md) | Vận hành hàng ngày, scheduler, monitoring, xử lý lỗi |
| [roadmap.md](roadmap.md) | Backlog, milestones, decisions log |

---

## Trạng thái hiện tại (cập nhật: 2026-04-01)

| Target | Trạng thái | Ghi chú |
|--------|-----------|---------|
| `fastdx_page` | ✅ Hoạt động | Token vĩnh viễn, đang schedule |
| `gtemas_jsc_page` | ✅ Hoạt động | Token vĩnh viễn |
| `gtemas_careers_page` | ⚠️ Token hết hạn | Cần renew GTEMAS_CAREERS_TOKEN |
| `linkedin_profile` | 🔴 Chưa setup | Cần LINKEDIN_ACCESS_TOKEN |
| `fastdx_linkedin` | 🔴 Chưa setup | Cần LINKEDIN_COMPANY_TOKEN + company_id |
| `personal_profile` | ⏸️ Tắt | Cần test manual lần đầu |
| `tech_group` | ⏸️ Tắt | Cần Group token + admin approve |

---

## Quick Commands

```bash
# Chạy scheduler
python cli.py run

# Đăng thử không lưu
python cli.py post -t fastdx_page --dry-run

# Research từ URL và xem trước
python cli.py research --topic "..." --url https://... --dry-run

# Xem bài chờ duyệt
python cli.py review

# Kiểm tra token
python cli.py validate

# Thống kê
python cli.py stats
```
