# Hướng dẫn Cấu hình Hệ thống ⚙️

Social Agent sử dụng cấu trúc cấu hình module hóa qua các file YAML. Thay vì một file `config.yaml` khổng lồ, dữ liệu được chia nhỏ vào các thư mục để quản lý đa tài khoản (multi-tenant) hiệu quả.

---

## 🏗️ Cấu trúc Module

Dữ liệu được chia thành các lớp chuyên biệt, giúp bạn quản lý hàng chục page/group mà không làm rối hệ thống:
1.  `profiles/`: Các "thân phận" hoặc tài khoản mạng xã hội (Access Token, Branding cụ thể).
2.  `topics/`: Các chủ đề nghiên cứu (Keywords, Description). Các profile có thể dùng chung Topics.
3.  `formats/`: Cấu trúc bài viết (Story, Leading, Insight, v.v.).

---

## 1. Cấu hình Global (`config.yaml`)

File này nằm ở thư mục gốc, chứa các thiết lập chung cho các Agent:

```yaml
llm:
  provider: gemini
  model: gemini-2.0-flash            # Model ID (gemini, openai, anthropic)
  temperature: 0.7                   # Độ sáng tạo
  max_tokens: 4096                   # Tránh bị ngắt quãng do bài viết quá dài

scheduler:
  timezone: "Asia/Ho_Chi_Minh"       # Múi giờ chạy lịch đăng bài
  misfire_grace_time: 300            # Cho phép trễ tối đa 5 phút
  coalesce: true                     # Gộp các job bị lỡ thành 1 lần chạy
```

---

## 2. Cấu hình Tài khoản (`profiles/`)

Mỗi tài khoản (Facebook Page, LinkedIn, Group) được định nghĩa trong một file `.yaml` riêng tại thư mục `profiles/`. Điều này cho phép mỗi tài khoản có tiếng nói (Branding) riêng biệt.

### Ví dụ: `profiles/ten_thuong_hieu.yaml`
```yaml
id: my_brand_page                    # ID dùng trong CLI: --target my_brand_page
type: page                           # page | group | linkedin_profile | linkedin_company
name: "Tên thương hiệu Page"
target_id: "123456789012345"         # ID của Page/Group/Company

# Branding (Cá nhân hóa nội dung)
brand_name: "Tên Thương Hiệu"        # AI sẽ ký tên này trong bài
tagline: "Khẩu hiệu/Slogan thương hiệu"
website: "https://tenmiencuaban.com" # Link dùng trong các lời kêu gọi hành động (CTA)
hashtags: [HashTag1, HashTag2]       # Các hashtag mặc định luôn xuất hiện

access_token: "${MY_BRAND_TOKEN}"    # Biến môi trường lấy từ .env
schedule: "0 8,18 * * *"             # Lịch đăng (Cron format)
review_mode: true                    # Bật để bài đi vào hàng chờ duyệt (Review Queue)
enabled: true                        # Cho phép scheduler nạp tài khoản này
```

---

## 3. Cấu hình Chủ đề (`topics/`)

Các Profile có thể đăng bài từ các Topic giống hoặc khác nhau tùy theo config trong profile.

### Ví dụ: `topics/marketing_ai.yaml`
```yaml
id: marketing_ai
name: "AI trong Marketing"
description: "Ứng dụng AI để tối ưu hóa chiến dịch quảng cáo và sáng tạo nội dung"
keywords: [MarketingAI, Chatbot, ContentAutomation]
language: vi

# Research (Tùy chọn nguồn nghiên cứu cố định)
research:
  urls: ["https://web-nguon.com/blog"]
  fb_pages: ["fanpage.doi.thu"]
```

---

## 4. Tự động gia hạn Token

Sử dụng lệnh sau để AI tự động refreshtoken cho tất cả profiles mà không cần làm tay:
```bash
social-agent token --refresh-all --save
```

---

## 💡 Quy trình mở rộng (Best Practices)
-   **Độc lập**: Thiết kế mỗi Profile YAML như một thực thể độc lập.
-   **Học tập**: Sử dụng `review_mode: true` cho các profile mới để AI học phong cách của bạn truớc khi cho đăng tự động 100%.
-   **Kiểm tra**: Luôn dùng `social-agent validate` sau khi thêm/sửa file config.
