# Roadmap & Backlog

---

## 🏗️ Trạng thái: April 2026 (Cập nhật 03-Apr)

### ✅ Đã hoàn thành (Phase 3: Autonomous Learning & Modular Architecture)

- [x] **Modular Configuration**: Tách config.yaml khổng lồ thành thư mục `profiles/`, `topics/`, `formats/`.
- [x] **SQLite Persistence**: Chuyển toàn bộ Review Queue, Audit Log, và Registry sang SQLite (`social_agent.db`).
- [x] **Dynamic Source Discovery**: Tự động tìm kiếm nguồn tin mới qua Gemini Search Grounding + FB Profile Discovery.
- [x] **Registry & Quality Scoring**: Theo dõi tỷ lệ Fetch thành công/thất bại của từng nguồn tin để tự động lọc.
- [x] **Three-Pillar Learning (Writing Memory)**: 
    - [x] Approved Samples: Học từ các bài viết được chấp nhận (Few-shot learning).
    - [x] Learned Rules: Tự đúc kết quy tắc từ lý do bị từ chối bài viết (Failure-based learning).
- [x] **Dynamic Branding**: Hashtags, URL, Brand Name, Tagline riêng biệt cho từng Profile.
- [x] **CLI Enhancements**: Thêm lệnh `discover`, `sources`, và cập nhật `review --reason`.

---

## 🔄 Đang triển khai (Phase 4: Interface & Intelligence)

### Ưu tiên cao (High Priority)

- [ ] **AI Reviewer (Pre-screening)**: 
  Sử dụng một Agent AI khác để tự đánh giá bài viết dựa trên rules trong Profile trước khi đưa cho con người duyệt. Tự động reject các bài rác.

- [ ] **Setup LinkedIn & Gtemas Tokens**: 
  Cập nhật token mới sau khi reset App Secret. Chạy `social-agent token --refresh-all`.

- [ ] **Telegram Bot Interface**:
  Nhận thông báo bài mới chờ duyệt qua Telegram, cho phép nhấn nút Approve/Reject và nhập lý do ngay trên điện thoại.

### Ưu tiên trung bình (Medium Priority)

- [ ] **Desktop GUI Dashboard**: 
  Xây dựng giao diện Desktop dựa trên `apps/desktop/` (PyWebView) để quản lý Profiles/Topics trực quan thay vì sửa YAML.

- [ ] **A/B Testing Content Patterns**:
  Track engagement (like/cmt/share) qua Facebook API và tự động điều chỉnh Format/Topic có hiệu quả cao nhất cho từng page.

- [ ] **Multi-language Expansion**:
  Cấu hình topics tiếng Anh chuyên sâu cho LinkedIn để tiếp cận khách hàng quốc tế.

---

## 📜 Decisions Log (Nhật ký quyết định)

| Ngày | Quyết định | Lý do |
|------|-----------|-------|
| 2026-04 | Chuyển sang Modular Folder | Quản lý Page/Topic quy mô lớn không làm rối config chính. |
| 2026-04 | SQLite cho tất cả data | Đảm bảo tính nhất quán (Atomicity), dễ query báo cáo và scale. |
| 2026-04 | Writing Memory (Rules + Samples) | Giải quyết bài toán AI viết bài bị "công thức", nhạt nhẽo và lặp lại lỗi. |
| 2026-04 | Dynamic Discovery | Giảm tải việc bảo trì danh sách URL nguồn thủ công. |

---

## ⚠️ Known Issues (Vấn đề tồn tồn tại)

- **LinkedIn Expired Tokens**: Cần login lại để lấy token 60 ngày.
- **FB App Review**: Các page/group ngoài tầm quản lý của owner app cần app review để post.
- **Image Generation Limit**: Gemini API free tier có giới hạn quota ảnh thấp hơn text.
