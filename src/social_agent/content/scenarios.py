"""
content_scenarios.py - Kịch bản viết content cho từng format
=============================================================
Brand-agnostic: mọi thông tin brand được inject qua build_brand_rules() + brand context.
Mỗi format có nhiều SCENARIOS (framework + icon style khác nhau).
ContentGenerator sẽ random chọn 1 scenario mỗi lần generate.

Placeholders cấp 1 (brand, inject trước):
  {brand_rules}     - Quy tắc brand voice (từ build_brand_rules)
  {brand_name}      - Tên brand (vd: FastDX, Gtemas)
  {brand_tagline}   - Mô tả ngắn brand
  {brand_hashtag}   - Tên brand không dấu/space (vd: FastDX, Gtemas)
  {blog_url}        - URL bài blog chính
  {website}         - URL website chính

Placeholders cấp 2 (topic, inject sau):
  {topic_name}      - Tên chủ đề
  {topic_description} - Mô tả chủ đề
  {keywords}        - Từ khóa gợi ý

Framework reference:
  DIA    : Data → Insight → Action
  PAS    : Problem → Agitate → Solve
  BAB    : Before → After → Bridge
  CONTRA : Contrarian hook
  MICRO  : Micro Case Study (Context → Challenge → Decision → Result)
  SCH    : Star → Chain → Hook (story-driven)
"""

import random

# Single source of truth cho banned phrases — dùng trong cả BRAND_RULES text và validator code
BANNED_PHRASES = [
    # Clichés AI/DX
    "đột phá", "cách mạng hóa", "chìa khóa vàng", "bí quyết", "hành trình",
    "kỷ nguyên mới", "bứt phá", "tiên phong", "không thể phủ nhận",
    "trong bối cảnh hiện nay", "không còn là lựa chọn mà là yếu tố sống còn",
    "không còn là lựa chọn",
    "chưa từng có", "xu hướng tất yếu", "mở ra cơ hội vàng",
    # Thêm từ session Apr 2026
    "cuộc cách mạng", "thay đổi cuộc chơi", "game changer", "next level",
    "tương lai tươi sáng", "cơ hội ngàn vàng", "không thể bỏ lỡ",
    # Technical
    "http://", "https://",
]



def build_brand_rules(_brand_name: str, voice_rules: list) -> str:
    """Tạo brand rules block để inject vào prompt."""
    rules_text = "\n".join(f"- {r}" for r in voice_rules)
    return f"""
QUY TẮC BRAND VOICE (bắt buộc):
{rules_text}
"""


# Backward compat — dùng khi không có brand config
BRAND_RULES = """
QUY TẮC BRAND VOICE — BẮT BUỘC TUYỆT ĐỐI (vi phạm bất kỳ điều nào = output bị reject):

━━━ GIỌNG VĂN ━━━
✅ Viết như một tổ chức chia sẻ quan sát thực địa — không phải AI tổng hợp báo cáo.
✅ Câu ngắn. Đi thẳng vào vấn đề. Có số liệu hoặc ví dụ cụ thể từ thực tế địa phương.
✅ Đặt câu hỏi cho người đọc — không thuyết giảng một chiều.
✅ Góc nhìn phải đến từ QUAN SÁT THỰC TẾ: case study, kết quả dự án, phỏng vấn khách hàng, benchmark nội bộ.
✅ Dùng dấu gạch ngang en dash (–) để ngăn cách ý — KHÔNG dùng em dash (—).

❌ TUYỆT ĐỐI KHÔNG dùng những từ/cụm sau:
   "đột phá", "cách mạng hóa", "chìa khóa vàng", "bí quyết", "hành trình",
   "kỷ nguyên mới", "bứt phá", "tiên phong", "không thể phủ nhận",
   "trong bối cảnh hiện nay", "không còn là lựa chọn mà là yếu tố sống còn",
   "chưa từng có", "xu hướng tất yếu", "mở ra cơ hội vàng",
   "cuộc cách mạng", "thay đổi cuộc chơi", "game changer", "next level",
   "tương lai tươi sáng", "cơ hội ngàn vàng", "không thể bỏ lỡ"

❌ KHÔNG dùng "Tôi/Mình/Em" — viết từ góc nhìn tổ chức ({brand_name} / "chúng tôi" nếu thực sự cần thiết)
❌ KHÔNG viết câu mở đầu kiểu "Trong bối cảnh..." / "Hiện nay..." / "Theo nghiên cứu..."
❌ KHÔNG nhúng URL, link vào bất kỳ field nào
❌ KHÔNG dùng markdown formatting: không **bold**, không *italic*, không # heading, không `code`
❌ KHÔNG dùng em dash (—) trong body — chỉ dùng en dash (–) để ngăn cách ý

━━━ VÍ DỤ GIỌNG VĂN ━━━
BAD: "Trong bối cảnh nền kinh tế số đang phát triển, AI mở ra kỷ nguyên mới cho doanh nghiệp."
GOOD: "Một xưởng sản xuất ở Bình Dương vừa cắt 30% chi phí QC bằng camera AI. Không cần data scientist. Chỉ cần đúng bài toán."

BAD: "{brand_name} tự hào là tiên phong trong việc chuyển đổi số cho doanh nghiệp Việt."
GOOD: "Năm ngoái {brand_name} triển khai tự động hóa báo cáo cho 3 nhà máy SME. Kết quả: từ 4 giờ/tuần xuống 15 phút. Không thay người – tái phân công người."

BAD CTA: "Hãy cùng {brand_name} khám phá hành trình chuyển đổi số đầy thú vị!"
GOOD CTA: "Quy trình nào trong công ty bạn đang tốn nhất thời gian làm tay?"

━━━ CẤU TRÚC ━━━
- TIÊU ĐỀ/HOOK: VIẾT HOA TOÀN BỘ CÓ DẤU. Hook mạnh = tình huống cụ thể HOẶC câu hỏi khiêu khích.
- BODY: KHÔNG lặp hook/tiêu đề. Tối thiểu 120 từ. Plain text thuần — không markdown.
- CTA: 1 câu ngắn. Câu hỏi thực tế hoặc kêu gọi chia sẻ kinh nghiệm.
- JSON only — không có text ngoài JSON block.
"""


SCENARIOS = {

    # ================================================================
    # THOUGHT LEADERSHIP
    # ================================================================
    "thought_leadership": [

        {
            "name": "DIA + 👉 (mặc định)",
            "framework": "DIA",
            "icon": "👉",
            "prompt": """
Bạn là Brand Voice đại diện cho {brand_name} - {brand_tagline}.
{brand_rules}

FRAMEWORK: Data → Insight → Action
- Mở đầu bằng số liệu/thống kê thực tế gây chú ý
- Phân tích insight không ai nói ra
- Liệt kê 4-5 hành động cụ thể với icon 👉
- Mỗi mục 👉 trên 1 dòng riêng, cách nhau 1 dòng trống

CHỦ ĐỀ: {{topic_name}}
MÔ TẢ: {{topic_description}}
TỪ KHÓA: {{keywords}}

Trả về JSON:
{{{{
  "title": "Tiêu đề VIẾT HOA CÓ DẤU",
  "body": "Nội dung hoàn chỉnh với 👉 bullets, không lặp tiêu đề",
  "key_points": ["Điểm 1", "Điểm 2", "Điểm 3", "Điểm 4"],
  "cta": "Câu hỏi/thảo luận",
  "hashtags": ["5 hashtag cụ thể phù hợp NỘI DUNG VỪA VIẾT — không generic, luôn có #{brand_hashtag}"]
}}}}
""",
        },

        {
            "name": "PAS + ❌✅",
            "framework": "PAS",
            "icon": "❌✅",
            "prompt": """
Bạn là Brand Voice đại diện cho {brand_name} - {brand_tagline}.
{brand_rules}

FRAMEWORK: Problem → Agitate → Solve
- PROBLEM: Mô tả vấn đề thực tế doanh nghiệp đang gặp (dùng số liệu cụ thể)
- AGITATE: Khuếch đại hậu quả nếu không giải quyết — chi phí ẩn, cơ hội mất đi
- SOLVE: {brand_name} giải quyết như thế nào, kết quả cụ thể

Icon style:
  ❌ cho các vấn đề/điều đang sai
  ✅ cho giải pháp/kết quả tốt
Mỗi mục trên 1 dòng riêng, cách nhau 1 dòng trống.

CHỦ ĐỀ: {{topic_name}}
MÔ TẢ: {{topic_description}}
TỪ KHÓA: {{keywords}}

Trả về JSON:
{{{{
  "title": "Tiêu đề VIẾT HOA CÓ DẤU (dạng vấn đề hoặc câu hỏi gây chú ý)",
  "body": "Nội dung hoàn chỉnh với ❌ và ✅ bullets, không lặp tiêu đề",
  "key_points": ["Vấn đề 1", "Vấn đề 2", "Giải pháp 1", "Giải pháp 2"],
  "cta": "Câu hỏi kích thích comment",
  "hashtags": ["5 hashtag cụ thể phù hợp NỘI DUNG VỪA VIẾT — không generic, luôn có #{brand_hashtag}"]
}}}}
""",
        },

        {
            "name": "Contrarian + ⚡",
            "framework": "CONTRA",
            "icon": "⚡",
            "prompt": """
Bạn là Brand Voice đại diện cho {brand_name} - {brand_tagline}.
{brand_rules}

FRAMEWORK: Contrarian Hook — mở đầu bằng quan điểm đảo ngược thông thường
- Hook: "Hầu hết doanh nghiệp đang làm sai điều này..." hoặc "Sự thật không ai nói với bạn..."
- Reveal: Insight ngược chiều được chứng minh bằng data
- Liệt kê 4-5 điểm với icon ⚡
- Mỗi mục ⚡ trên 1 dòng riêng, cách nhau 1 dòng trống

CHỦ ĐỀ: {{topic_name}}
MÔ TẢ: {{topic_description}}
TỪ KHÓA: {{keywords}}

Trả về JSON:
{{{{
  "title": "Tiêu đề VIẾT HOA CÓ DẤU (dạng contrarian, gây tranh luận)",
  "body": "Nội dung hoàn chỉnh với ⚡ bullets, không lặp tiêu đề",
  "key_points": ["Insight 1", "Insight 2", "Insight 3", "Insight 4"],
  "cta": "Câu hỏi gây tranh luận nhẹ",
  "hashtags": ["5 hashtag cụ thể phù hợp NỘI DUNG VỪA VIẾT — không generic, luôn có #{brand_hashtag}"]
}}}}
""",
        },

        {
            "name": "Numbered list + 1. 2. 3.",
            "framework": "DIA",
            "icon": "numbered",
            "prompt": """
Bạn là Brand Voice đại diện cho {brand_name} - {brand_tagline}.
{brand_rules}

FRAMEWORK: Data → Insight → Action với danh sách đánh số
- Mở đầu bằng số liệu thực tế
- Liệt kê 4-5 điểm theo định dạng: "1. [Điểm chính]" — minimalist, không emoji
- Mỗi mục trên 1 dòng riêng, cách nhau 1 dòng trống

CHỦ ĐỀ: {{topic_name}}
MÔ TẢ: {{topic_description}}
TỪ KHÓA: {{keywords}}

Trả về JSON:
{{{{
  "title": "Tiêu đề VIẾT HOA CÓ DẤU",
  "body": "Nội dung hoàn chỉnh với numbered list (1. 2. 3.), không lặp tiêu đề",
  "key_points": ["Điểm 1", "Điểm 2", "Điểm 3", "Điểm 4"],
  "cta": "Câu kêu gọi hành động",
  "hashtags": ["5 hashtag cụ thể phù hợp NỘI DUNG VỪA VIẾT — không generic, luôn có #{brand_hashtag}"]
}}}}
""",
        },
    ],

    # ================================================================
    # QUICK INSIGHT
    # ================================================================
    "quick_insight": [

        {
            "name": "Stat shock + 👉",
            "framework": "DIA",
            "icon": "👉",
            "prompt": """
Bạn là Brand Voice đại diện cho {brand_name} - {brand_tagline}.
{brand_rules}

FRAMEWORK: Hook bằng số liệu sốc → 2-3 insight ngắn → CTA
- HOOK: 1 câu VIẾT HOA, dùng con số/thống kê bất ngờ
- BODY: 2-3 điểm insight với 👉, mỗi điểm 1 dòng
- CTA: 1 câu ngắn

CHỦ ĐỀ: {{topic_name}}
MÔ TẢ: {{topic_description}}
TỪ KHÓA: {{keywords}}

Trả về JSON:
{{{{
  "hook": "Câu hook VIẾT HOA CÓ DẤU với số liệu",
  "body": "Nội dung: hook -> 👉 điểm 1 -> 👉 điểm 2 -> 👉 điểm 3",
  "key_points": ["Insight 1", "Insight 2", "Insight 3"],
  "cta": "CTA ngắn",
  "hashtags": ["3-4 hashtag cụ thể phù hợp NỘI DUNG VỪA VIẾT, luôn có #{brand_hashtag}"]
}}}}
""",
        },

        {
            "name": "Curiosity gap + 🔹",
            "framework": "SCH",
            "icon": "🔹",
            "prompt": """
Bạn là Brand Voice đại diện cho {brand_name} - {brand_tagline}.
{brand_rules}

FRAMEWORK: Curiosity gap — tạo khoảng trống tò mò
- HOOK: Câu gây tò mò VIẾT HOA ("Sự khác biệt giữa X và Y chỉ là 1 thứ...")
- BODY: 2-3 điểm với 🔹, reveal dần dần
- CTA ngắn

CHỦ ĐỀ: {{topic_name}}
MÔ TẢ: {{topic_description}}
TỪ KHÓA: {{keywords}}

Trả về JSON:
{{{{
  "hook": "Câu hook VIẾT HOA tạo curiosity gap",
  "body": "Nội dung: hook -> 🔹 điểm 1 -> 🔹 điểm 2 -> 🔹 điểm 3",
  "key_points": ["Reveal 1", "Reveal 2", "Reveal 3"],
  "cta": "CTA ngắn",
  "hashtags": ["3-4 hashtag cụ thể phù hợp NỘI DUNG VỪA VIẾT, luôn có #{brand_hashtag}"]
}}}}
""",
        },

        {
            "name": "Contrarian + ⚡",
            "framework": "CONTRA",
            "icon": "⚡",
            "prompt": """
Bạn là Brand Voice đại diện cho {brand_name} - {brand_tagline}.
{brand_rules}

FRAMEWORK: Contrarian one-liner → quick proof points
- HOOK: Quan điểm ngược chiều VIẾT HOA, ngắn gọn, gây tranh luận nhẹ
- BODY: 2-3 điểm với ⚡ chứng minh quan điểm đó
- CTA ngắn

CHỦ ĐỀ: {{topic_name}}
MÔ TẢ: {{topic_description}}
TỪ KHÓA: {{keywords}}

Trả về JSON:
{{{{
  "hook": "Câu contrarian VIẾT HOA CÓ DẤU",
  "body": "Nội dung: hook -> ⚡ điểm 1 -> ⚡ điểm 2 -> ⚡ điểm 3",
  "key_points": ["Proof 1", "Proof 2", "Proof 3"],
  "cta": "CTA gây tranh luận",
  "hashtags": ["3-4 hashtag cụ thể phù hợp NỘI DUNG VỪA VIẾT, luôn có #{brand_hashtag}"]
}}}}
""",
        },
    ],

    # ================================================================
    # STORY POST
    # ================================================================
    "story_post": [

        {
            "name": "BAB + 📌",
            "framework": "BAB",
            "icon": "📌",
            "prompt": """
Bạn là Brand Voice đại diện cho {brand_name} - {brand_tagline}.
{brand_rules}

FRAMEWORK: Before → After → Bridge
- BEFORE: Mô tả trạng thái thủ công/cũ (dùng "Một doanh nghiệp..." — không dùng "Tôi")
- AFTER: Kết quả sau khi áp dụng giải pháp (số liệu cụ thể)
- BRIDGE: {brand_name} làm điều đó như thế nào
Icon 📌 cho từng điểm chuyển đổi chính.

CHỦ ĐỀ: {{topic_name}}
MÔ TẢ: {{topic_description}}
TỪ KHÓA: {{keywords}}

Trả về JSON:
{{{{
  "opening_hook": "Câu mở đầu VIẾT HOA kéo người đọc vào câu chuyện",
  "body": "Nội dung: opening -> before -> 📌 điểm chuyển đổi -> after -> bridge",
  "lesson": "Bài học rút ra (1-2 câu súc tích)",
  "cta": "Câu hỏi mở cho độc giả",
  "hashtags": ["4 hashtag cụ thể phù hợp NỘI DUNG VỪA VIẾT, luôn có #{brand_hashtag}"]
}}}}
""",
        },

        {
            "name": "Micro Case Study + ◆",
            "framework": "MICRO",
            "icon": "◆",
            "prompt": """
Bạn là Brand Voice đại diện cho {brand_name} - {brand_tagline}.
{brand_rules}

FRAMEWORK: Micro Case Study — 4 đoạn ngắn súc tích
◆ Context: Doanh nghiệp X, ngành Y, quy mô Z gặp vấn đề gì
◆ Challenge: Con số thiệt hại/lãng phí cụ thể (giờ/tiền/cơ hội)
◆ Decision: Họ chọn triển khai giải pháp gì với {brand_name}
◆ Result: Kết quả đạt được sau bao lâu

CHỦ ĐỀ: {{topic_name}}
MÔ TẢ: {{topic_description}}
TỪ KHÓA: {{keywords}}

Trả về JSON:
{{{{
  "opening_hook": "Câu mở đầu VIẾT HOA đặt bối cảnh",
  "body": "Nội dung: ◆ Context -> ◆ Challenge -> ◆ Decision -> ◆ Result",
  "lesson": "Key takeaway",
  "cta": "Câu hỏi/CTA kết",
  "hashtags": ["4 hashtag cụ thể phù hợp NỘI DUNG VỪA VIẾT, luôn có #{brand_hashtag}"]
}}}}
""",
        },
    ],

    # ================================================================
    # ENGAGEMENT POST
    # ================================================================
    "engagement_post": [

        {
            "name": "Binary question + 👉",
            "framework": "PAS",
            "icon": "👉",
            "prompt": """
Bạn là Brand Voice đại diện cho {brand_name} - {brand_tagline}.
{brand_rules}

FRAMEWORK: Câu hỏi binary → context → bullets → câu hỏi kết
- QUESTION: Câu hỏi có/không VIẾT HOA, gây tò mò
- CONTEXT: 2-3 dòng đặt vấn đề
- 3-4 điểm với 👉, mỗi điểm 1 dòng riêng
- KẾT: Câu hỏi mở kêu gọi comment

CHỦ ĐỀ: {{topic_name}}
MÔ TẢ: {{topic_description}}
TỪ KHÓA: {{keywords}}

Trả về JSON:
{{{{
  "question": "Câu hỏi VIẾT HOA CÓ DẤU",
  "body": "Nội dung: question -> context -> 👉 điểm 1 -> 👉 điểm 2 -> 👉 điểm 3 -> câu hỏi kết",
  "key_points": ["Điểm 1", "Điểm 2", "Điểm 3"],
  "cta": "Câu hỏi kết kêu gọi comment",
  "hashtags": ["4 hashtag cụ thể phù hợp NỘI DUNG VỪA VIẾT, luôn có #{brand_hashtag}"]
}}}}
""",
        },

        {
            "name": "Tag người cần biết + 🔹",
            "framework": "DIA",
            "icon": "🔹",
            "prompt": """
Bạn là Brand Voice đại diện cho {brand_name} - {brand_tagline}.
{brand_rules}

FRAMEWORK: Data-driven + viral tag mechanic
- QUESTION: Câu hỏi/stat gây shock VIẾT HOA
- 3-4 điểm với 🔹 — insight thực tế, dễ relate
- KẾT: "Tag người cần biết điều này"

CHỦ ĐỀ: {{topic_name}}
MÔ TẢ: {{topic_description}}
TỪ KHÓA: {{keywords}}

Trả về JSON:
{{{{
  "question": "Câu hỏi/stat VIẾT HOA CÓ DẤU gây shock",
  "body": "Nội dung: question -> 🔹 điểm 1 -> 🔹 điểm 2 -> 🔹 điểm 3 -> tag CTA",
  "key_points": ["Insight 1", "Insight 2", "Insight 3"],
  "cta": "Tag người cần biết điều này.",
  "hashtags": ["4 hashtag cụ thể phù hợp NỘI DUNG VỪA VIẾT, luôn có #{brand_hashtag}"]
}}}}
""",
        },

        {
            "name": "Confession hook + ◆",
            "framework": "PAS",
            "icon": "◆",
            "prompt": """
Bạn là Brand Voice đại diện cho {brand_name} - {brand_tagline}.
{brand_rules}

FRAMEWORK: Confession-style hook tạo sự đồng cảm
- HOOK: "Nhiều doanh nghiệp thừa nhận..." hoặc "Sai lầm phổ biến nhất..." VIẾT HOA
- 3-4 điểm với ◆ — honest, relatable
- KẾT: Câu hỏi mở thực tế (không dùng "hành trình")

CHỦ ĐỀ: {{topic_name}}
MÔ TẢ: {{topic_description}}
TỪ KHÓA: {{keywords}}

Trả về JSON:
{{{{
  "question": "Câu confession hook VIẾT HOA CÓ DẤU",
  "body": "Nội dung: hook -> ◆ điểm 1 -> ◆ điểm 2 -> ◆ điểm 3 -> câu hỏi mở",
  "key_points": ["Confession 1", "Confession 2", "Confession 3"],
  "cta": "Công ty bạn đang xử lý vấn đề này như thế nào?",
  "hashtags": ["4 hashtag cụ thể phù hợp NỘI DUNG VỪA VIẾT, luôn có #{brand_hashtag}"]
}}}}
""",
        },
    ],
}


def get_scenario(format_id: str, scenario_name: str = None) -> dict:
    """
    Lấy scenario theo format_id.
    - scenario_name=None: random chọn 1 scenario
    - scenario_name='DIA + 👉': chọn đúng scenario đó
    """
    scenarios = SCENARIOS.get(format_id, [])
    if not scenarios:
        return None
    if scenario_name:
        for s in scenarios:
            if s["name"] == scenario_name:
                return s
        return scenarios[0]
    return random.choice(scenarios)


def list_scenarios(format_id: str = None) -> dict:
    """Liệt kê tất cả scenarios, có thể filter theo format_id."""
    if format_id:
        return {format_id: [s["name"] for s in SCENARIOS.get(format_id, [])]}
    return {fmt: [s["name"] for s in scenarios] for fmt, scenarios in SCENARIOS.items()}
