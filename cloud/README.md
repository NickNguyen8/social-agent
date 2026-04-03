# Cloud — Paid Tier (Future)

Thư mục này chứa phần cloud của Social Agent (tính năng trả phí).

## Stack dự kiến
- `backend/` — NestJS API server
- `frontend/` — NextJS web app

## Tính năng paid
- Reports nâng cao & export
- Multi-device sync (đồng bộ dữ liệu từ local app)
- Team collaboration
- Scheduler cloud 24/7 (không cần VPS riêng)
- Analytics dashboard

## Data Integration
Local app (SQLite) sẽ sync lên cloud qua REST API của NestJS backend.
Schema đã được chuẩn hóa từ đầu để hỗ trợ migration dễ dàng.

## Status
Chưa build — placeholder only.
