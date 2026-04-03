# Chiến lược nội dung

## Brand Voice FastDX

**FastDX** là đơn vị tư vấn DX & AI thực chiến tại Việt Nam.  
Mọi bài viết phải thể hiện: **thực dụng → cụ thể → ROI rõ ràng**.

### Quy tắc bắt buộc (hardcoded trong mọi prompt)

| Quy tắc | Lý do |
|---------|-------|
| KHÔNG dùng "Tôi/Mình/Em" | Brand voice khách quan, không cá nhân hóa |
| KHÔNG dùng "Zalo-first" | Đã banned nội bộ (overused, clichéd) |
| KHÔNG lặp tiêu đề trong body | Formatter tự strip, nhưng LLM cũng được dặn |
| TIÊU ĐỀ VIẾT HOA CÓ DẤU | Nổi bật trên feed |
| Dùng 👉 cho bullet points | Consistent visual style |
| Kết thúc bằng fastdx.dev link | Luôn có CTA về website |

---

## Topics hiện có

| ID | Chủ đề | Dùng cho |
|----|--------|---------|
| `ai_vietnam` | AI tại Việt Nam | Xu hướng, ứng dụng AI tại VN |
| `dx_consulting` | Chuyển Đổi Số Thực Chiến | FastDX consulting, ROI, SME |
| `agentic_ai` | Agentic AI Systems | Autonomous agents, AI workforce |
| `zalo_os` | Zalo-as-an-OS | Tối ưu Zalo làm nền tảng vận hành |
| `legacy_mod` | Legacy Modernization | Từ Excel/Zalo → AI-native |
| `arch_audit` | Architecture & Security Audit | Tech debt, scale, security |
| `fintech_sea` | Fintech Đông Nam Á | Digital banking, payments |
| `leadership_tech` | Lãnh đạo công nghệ | CTO, team scaling, consulting |

### Thêm topic mới

```yaml
# config.yaml
topics:
  - id: my_new_topic
    name: "Tên hiển thị"
    description: "Mô tả đủ context để LLM hiểu góc nhìn và đối tượng"
    keywords: ["kw1", "kw2"]
    language: vi
    research:              # Tuỳ chọn
      urls: ["https://..."]
```

---

## Formats & Scenarios

### 4 Formats

**1. `thought_leadership`** — Bài chuyên môn sâu  
Cấu trúc: `TIÊU ĐỀ` → body (4-5 điểm 👉) → hashtags  
Phù hợp: chia sẻ insight, prediction, framework

**2. `quick_insight`** — Hook nhanh  
Cấu trúc: Hook gây tò mò → 3 điểm súc tích → CTA + link  
Phù hợp: engagement cao, viral potential

**3. `story_post`** — Kể chuyện  
Cấu trúc: Opening hook → diễn biến (trước/sau) → bài học → CTA  
Phù hợp: case study, transformation story

**4. `engagement_post`** — Kích thích tương tác  
Cấu trúc: Câu hỏi → context → 3-4 điểm 👉 → câu hỏi kết + link  
Phù hợp: poll, discussion, comment farming

---

### 12 Scenarios (trong `content_scenarios.py`)

Mỗi format có nhiều scenario — được chọn ngẫu nhiên mỗi lần generate:

#### `thought_leadership` (4 scenarios)
| Tên | Framework | Icon style |
|-----|-----------|-----------|
| DIA + 👉 | Disruption → Impact → Action | 👉 |
| PAS + ❌✅ | Problem → Agitate → Solve | ❌ ✅ |
| Contrarian + ⚡ | Góc nhìn ngược | ⚡ |
| Numbered list | 1. 2. 3. | Số thứ tự |

#### `quick_insight` (3 scenarios)
| Tên | Đặc điểm |
|-----|---------|
| Stat-led | Mở bằng con số gây sốc |
| Question-led | Mở bằng câu hỏi |
| Micro-list + 📌 | Danh sách cực ngắn |

#### `story_post` (2 scenarios)
| Tên | Đặc điểm |
|-----|---------|
| Before/After + ◆ | Timeline transformation |
| BAB (Before-After-Bridge) | Cầu nối từ vấn đề → giải pháp |

#### `engagement_post` (3 scenarios)
| Tên | Đặc điểm |
|-----|---------|
| Poll-style + 🔹 | A vs B question |
| Hot-take | Tuyên bố controversial |
| Checklist + ✅ | Tự kiểm tra |

### Thêm scenario mới

Mở `content_scenarios.py` → thêm vào dict `SCENARIOS[format_id]`:

```python
{
    "name": "Tên scenario",
    "framework": "FRAMEWORK_KEY",
    "icon": "👉",   # hoặc "❌✅", "⚡", "numbered", "🔹", "◆", "📌", "✅"
    "prompt": """...""",
}
```

Prompt phải có placeholders: `{brand_rules}`, `{topic_name}`, `{topic_description}`, `{keywords}`.

---

## Lịch đăng gợi ý

| Target | Tần suất | Lý do |
|--------|---------|-------|
| FB Page (FastDX) | 2 lần/ngày (8h, 18h) | Giờ vàng Facebook VN |
| FB Page (Gtemas) | 1 lần/ngày (10h) | Không cạnh tranh với FastDX |
| LinkedIn | 1 lần/ngày làm việc | LinkedIn ít hơn FB |
| Personal Profile | 1 lần/ngày | Giữ an toàn, tránh checkpoint |

---

## Hashtag strategy

**Cố định (luôn có):** `#FastDX #DigitalTransformation #Vietnam #AgenticAI`  
**Theo format:** `#CaseStudy` (story), `#SMEs` (consulting), `#Fintech` (fintech_sea)  
**Theo topic:** `#AI #LLM #Automation` (ai_vietnam), `#ROI #Modernization` (dx_consulting)
