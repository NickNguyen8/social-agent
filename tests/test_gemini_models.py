"""
test_gemini_models.py - Script thủ công để liệt kê Gemini models khả dụng.
Chạy trực tiếp: python tests/test_gemini_models.py
KHÔNG chạy trong pytest CI (cần GEMINI_API_KEY thật).
"""

import os
import pytest

# Bỏ qua file này khi chạy pytest tự động (không có API key thật)
if not os.environ.get("GEMINI_API_KEY"):
    pytest.skip("GEMINI_API_KEY not set — skipping live model list", allow_module_level=True)


def test_list_gemini_models():
    """List all Gemini models that support generateContent."""
    import google.generativeai as genai
    from dotenv import load_dotenv

    load_dotenv()
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])

    models = [
        m.name
        for m in genai.list_models()
        if "generateContent" in m.supported_generation_methods
    ]
    assert len(models) > 0, "Không tìm thấy model nào hỗ trợ generateContent"
    print("\n--- Gemini models khả dụng ---")
    for name in models:
        print(f"  {name}")
