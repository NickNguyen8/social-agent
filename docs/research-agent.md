# Research Agent 🔍

Agent tự động tìm kiếm, thu thập và đúc kết nội dung từ Internet và mạng xã hội để tạo ra các bài viết có chiều sâu, số liệu thực tế và cập nhật cho bất kỳ thương hiệu nào.

---

## 🚀 Hai cơ chế thu thập nguồn tin

### 1. Nguồn tin Cố định (Static Seeds)
Được định nghĩa trong các file tại thư mục `topics/`. Đây là các URL hoặc Fanpage "ruột" mà bạn tin tưởng chất lượng nội dung.

```yaml
# topics/ai_vietnam.yaml
research:
  urls: ["https://vnexpress.net/so-hoa/ai"]
  fb_pages: ["fanpage.chuyen.mon"]
```

### 2. Nguồn tin Tự động (Dynamic Discovery) 🌟
Đây là bước tiến quan trọng, giúp hệ thống không phụ thuộc vào các link chết. Sử dụng lệnh:

```bash
social-agent discover --topic branding_digital
```

Agent sẽ thực hiện:
- **Web Search**: Dùng Gemini Grounding để tìm các bài báo, nghiên cứu mới nhất theo keywords của Topic.
- **Social Discovery**: Tìm các Facebook Page/Group có tương tác cao liên quan đến chủ đề.
- **Registry & Scoring**: Lưu các nguồn tìm được vào SQLite. Mỗi lần fetch, hệ thống sẽ chấm điểm (success/fail). Nguồn tin rác hoặc link chết sẽ tự động bị loại bỏ khỏi danh sách ưu tiên.

---

## 🛠️ Quy trình xử lý (Pillar 1)

1.  **Fetching (Song song)**: `WebFetcher` và `FBPageFetcher` truy cập đồng thời vào danh sách URLs/Pages.
2.  **Summarizing (BriefSummarizer)**: Gemini đọc toàn bộ nội dung thô (raw content) và trích xuất thành một `ResearchBrief` JSON.
3.  **Synthesizing**: `ContentGenerator` nhận `ResearchBrief` để viết bài, đảm bảo nội dung dựa trên số liệu/insights thực tế thay vì dự đoán của LLM.

---

## 📊 Cấu trúc Research Brief

```python
{
    "key_insights": ["Insight 1", "Insight 2"],
    "notable_stats": ["Số liệu 1", "Số liệu 2"],
    "content_angles": ["Góc nhìn A", "Góc nhìn B"],
    "summary": "Tóm tắt 3 câu về bối cảnh hiện tại...",
    "source_quality": "high",  # Đánh giá độ tin cậy của nguồn
    "web_excerpts": [...],     # Trích dẫn thô từ web
    "facebook_posts": [...]    # Các bài đăng social gần đây
}
```

---

## 💡 Tips tối ưu Research

-   **Keyword chất lượng**: Thay vì "AI", hãy dùng "Xu hướng Agentic AI cho doanh nghiệp 2025" trong file `topics/`.
-   **Validation**: Thường xuyên chạy `social-agent sources` để kiểm tra danh sách nguồn tin mà AI đã tự khám phá được cho từng chủ đề.
-   **Feedback Loop**: Khi bạn Approve một bài viết dựa trên research tốt, hệ thống sẽ ghi nhận style đó. Nếu bạn Reject vì thông tin sai, hãy ghi rõ lý do để AI học cách lọc nguồn tốt hơn.

---

## 📝 CLI Manual Research

Nếu bạn muốn Research thủ công cho một bài viết đơn lẻ từ một nguồn cụ thể:
```bash
social-agent research \
  --topic "Chủ đề nghiên cứu" \
  --url https://source.com/article \
  --fb-page some.page \
  --target brand_page \
  --dry-run
```
