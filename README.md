# Autonomous Multi-Account Social Agent 🤖

Hệ thống Agentic AI mạnh mẽ quản lý đồng thời hàng chục tài khoản mạng xã hội (Facebook, LinkedIn, Groups) với khả năng nghiên cứu tự động và tự tối ưu hóa theo thời gian.

---

## 🏗️ Kiến trúc Đa Agent & Đa Tài khoản (Multi-Tenant Architecture)

Social Agent được thiết kế để phục vụ doanh nghiệp quản lý nhiều thương hiệu khác nhau. Thay vì cấu hình cứng, hệ thống tách biệt hoàn toàn:
1.  **Profiles**: Nằm trong `profiles/`. Mỗi profile là một "nhân sự số" độc lập (Access Tokens, Brand Name, Tagline, URL).
2.  **Topics**: Nằm trong `topics/`. Các profile có thể dùng chung hoặc dùng riêng các chủ đề nghiên cứu này.
3.  **Writing Memory**: AI học phong cách viết riêng cho từng cặp `(Profile, Topic)`. AI sẽ viết kiểu "Tuyển dụng" khác hoàn toàn với kiểu "Tư vấn chuyên gia".

---

## 🌟 Tính năng "Học liên tục" (Continuous Learning)

Hệ thống áp dụng 3 vòng lặp học tập để AI ngày càng thông minh:
-   **Research Loop**: Tự động khám phá nguồn tin (URLs, FB Pages) và đánh giá chất lượng.
-   **Writing Memory**: AI ghi nhớ bài đã duyệt (Few-shot) và đúc kết quy tắc từ bài bị từ chối (Rejection rules).
-   **Review Logic**: Gatekeeper đảm bảo chất lượng và tạo tín hiệu phản hồi để hệ thống tự tối ưu.

---

## 🛠️ Cài đặt & Setup lần đầu

```bash
# Cài đặt
git clone https://github.com/nicknguyen8/social-agent
cd social-agent
pip install -e .

# Setup:
# 1. Copy .env.example → .env và điền GEMINI_API_KEY.
# 2. Chạy validate để kiểm tra targets/tokens
social-agent validate

# 3. Chạy discover để AI tự build danh sách nguồn tin đầu tiên
social-agent discover
```

---

## 🚀 Sử dụng CLI

### 🔍 Discovery & Research
```bash
# Tìm nguồn tin mới cho topic 'ai_vietnam'
social-agent discover -t ai_vietnam

# Xem danh sách nguồn tin và điểm chất lượng registry
social-agent sources -t ai_vietnam
```

### ✍️ Content Generation
```bash
# Đăng ngay (hoặc đẩy vào queue nếu review_mode bật)
social-agent post --target my_brand_page

# Preview nội dung (không đăng)
social-agent preview --target my_brand_page --format quick_insight
```

### 🔎 Review & Dạy AI (Feedback Loop)
```bash
# Xem các bài đang chờ duyệt
social-agent review

# Duyệt và đăng bài
social-agent review --approve abc123

# Từ chối và dạy AI (Quan trọng nhất)
social-agent review --reject abc123 --reason "Tránh dùng từ 'đột phá', hãy dùng ngôi thứ nhất"
```

---

## 📂 Quản lý Profile & Dữ liệu

Hệ thống tự động quét folder để nạp dữ liệu:
-   `profiles/`: Folder chứa tài khoản, Target IDs, Tokens, và Branding đặc thù.
-   `topics/`: Định nghĩa từ khóa và mô tả chủ đề để AI đi nghiên cứu.
-   `formats/`: Các mẫu cấu trúc bài viết (Story, Leading, Insight, v.v.).
-   `data/social_agent.db`: "Bộ não" SQLite chứa mọi ký ức của các Agent.

---

© 2026 Social Agent Framework.
