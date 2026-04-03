# Token & Credentials Management 🔑

Hệ thống cung cấp cơ chế quản lý Token tự động để đảm bảo việc đăng bài không bị gián đoạn do Token hết hạn.

---

## 🚀 Quản lý Tự động (Auto-Refresh)

Bạn không cần phải copy tay Token từ Facebook Graph Explorer mỗi tháng nữa. Sau khi lắp đặt `FB_APP_ID`, `FB_APP_SECRET` và một cái `FB_USER_TOKEN` (Long-lived) vào `.env`:

1.  **Lệnh gia hạn thủ công**: 
    ```bash
    social-agent token --refresh-all --save
    ```
    Lệnh này sẽ tự động lấy Token mới cho tất cả các Pages trong Profile của bạn và lưu thẳng vào file `.env`.

2.  **Tự động gia hạn (Scheduler)**:
    Mỗi khi chạy `social-agent run`, hệ thống sẽ tự động gia hạn các tokens này định kỳ vào lúc 07:00 thứ 2 hàng tuần (nếu được cấu hình).

---

## 🛠️ Thiết lập lần đầu (Setup Guide)

### 1. Google Gemini API Key
-   Lấy tại: [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
-   Dán vào `.env`: `GEMINI_API_KEY=AIzaSy...`

### 2. Facebook Graph API (Pages & Groups)
Để lấy Token không bao giờ hết hạn:
-   **Bước 1**: Tạo Facebook App (Business Type) tại [developers.facebook.com](https://developers.facebook.com). Ghi lại `FB_APP_ID` và `FB_APP_SECRET`.
-   **Bước 2**: Tại Graph Explorer, lấy một **User Access Token** (Short-lived) với các quyền:
    -   `pages_manage_posts`
    -   `pages_read_engagement`
    -   `pages_show_list`
-   **Bước 3**: Chạy lệnh setup:
    ```bash
    social-agent token --app-id [ID] --app-secret [SECRET] --user-token [SHORT_LIVED_TOKEN] --save
    ```
    Hệ thống sẽ tự động sinh ra các Page Tokens vĩnh viễn cho bạn.

### 3. LinkedIn (Personal & Company)
-   Truy cập: [LinkedIn Developers Portal](https://www.linkedin.com/developers/apps)
-   Tạo App → Auth → OAuth 2.0 Tools.
-   **Scopes cần thiết**: `openid`, `profile`, `w_member_social`, `w_organization_social` (nếu đăng cho Company).
-   Dán vào `.env`: `LINKEDIN_ACCESS_TOKEN=...` và `LINKEDIN_COMPANY_TOKEN=...`

### 4. Personal Profile (Chrome Automation)
Nếu muốn đăng lên Profile cá nhân mà không qua API (dễ bị flag):
-   Cần đường dẫn Profile Chrome thật của bạn:
    -   **macOS**: `/Users/[tên]/Library/Application Support/Google/Chrome`
    -   **Windows**: `C:\Users\[tên]\AppData\Local\Google\Chrome\User Data`
-   Dán vào `.env`: `FB_CHROME_PROFILE_PATH` và `FB_CHROME_PROFILE_DIR=Default`.
-   **Lưu ý**: Hãy đăng nhập thủ công trên Chrome trước khi chạy Agent.

---

## 📊 Kiểm tra trạng thái Token
Dùng lệnh sau để biết Token nào còn sống, Token nào đã chết:
```bash
social-agent validate
```
Hệ thống sẽ quét qua tất cả các file trong thư mục `profiles/` và kiểm tra quyền đăng bài thực tế.
