import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional, List

import requests
import yaml
from dotenv import load_dotenv

from social_agent.content.scenarios import BANNED_PHRASES, BRAND_RULES, get_scenario

load_dotenv()

logger = logging.getLogger("social_agent.content")

# Các trường bắt buộc cho từng format (dùng để validate LLM output)
REQUIRED_KEYS = {
    "thought_leadership": ["title", "body", "key_points", "cta", "hashtags"],
    "quick_insight": ["hook", "body", "key_points", "cta", "hashtags"],
    "story_post": ["opening_hook", "body", "lesson", "cta", "hashtags"],
    "engagement_post": ["question", "body", "key_points", "cta", "hashtags"]
}


class ContentGenerator:
    def __init__(self, config_path: str = "config.yaml"):
        # Load global config
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f)
        except Exception:
            self.config = {"llm": {"provider": "gemini", "model": "gemini-2.0-flash"}}

        llm_cfg = self.config.get("llm", {})
        self.provider = llm_cfg.get("provider", "gemini")
        self.model_name = llm_cfg.get("model", "gemini-2.0-flash")
        self.temperature = llm_cfg.get("temperature", 0.7)
        self.max_tokens = llm_cfg.get("max_tokens", 2048)

        # Load data from directories (Pillar 1 refactor)
        self._load_data()
        
        # Pillar 2: Writing Memory
        from social_agent.storage.sqlite import WritingMemoryDB
        self.writing_memory = WritingMemoryDB()

        self.api_key = os.environ.get("GEMINI_API_KEY")

    def _load_data(self):
        """Load topics và formats từ các thư mục riêng lẻ."""
        from social_agent.utils.paths import get_topics_dir
        
        # Topics
        self._topics = {}
        t_dir = get_topics_dir()
        # Fallback to local 'topics' folder if the system one is empty
        search_dirs = [t_dir, Path("topics")]
        for p in search_dirs:
            if p.exists():
                for f in p.glob("*.yaml"):
                    try:
                        with open(f, encoding="utf-8") as f_in:
                            data = yaml.safe_load(f_in)
                            if data and "id" in data:
                                self._topics[data["id"]] = data
                    except Exception: pass
        
        # Formats
        self._formats = {}
        f_dir = Path("formats")
        if f_dir.exists():
            for f in f_dir.glob("*.yaml"):
                try:
                    with open(f, encoding="utf-8") as f_in:
                        data = yaml.safe_load(f_in)
                        if data and "id" in data:
                            self._formats[data["id"]] = data
                except Exception: pass

    def _validate_content(self, content: dict) -> list[str]:
        """Kiểm tra output LLM có vi phạm brand rules không."""
        violations = []
        all_text = " ".join(str(v) for v in content.values() if isinstance(v, str)).lower()

        # Banned phrases logic
        from social_agent.content.scenarios import BANNED_PHRASES
        for phrase in BANNED_PHRASES:
            if phrase.lower() in all_text:
                violations.append(f"Chứa từ bị cấm: '{phrase}'")

        # Body length check (BRAND_RULES requirement)
        body = content.get("body") or content.get("opening_hook") or ""
        words = len(body.split())
        if words < 120:
            violations.append(f"Body quá ngắn ({words} từ, cần ≥ 120)")

        return violations

    def generate(self, topic_id: str, format_id: str, recent_titles: list = None, profile: dict = None) -> dict:
        topic = self._topics.get(topic_id)
        if not topic:
            raise ValueError(f"Topic {topic_id} không tồn tại")

        scenario = get_scenario(format_id)
        if not scenario:
            raise ValueError(f"Format {format_id} không tồn tại (không tìm thấy scenario)")

        # Fetch memory for continuous learning (Pillar 2)
        profile_id = profile.get("id") if profile else None
        memory = self.writing_memory.get(profile_id, topic_id) if profile_id else None

        prompt = self._build_prompt(scenario, topic, recent_titles=recent_titles, memory=memory, profile=profile)
        return self._generate_with_retry(prompt, format_id, scenario, topic, recent_titles, profile=profile)

    def generate_from_brief(self, brief: dict, format_id: str, recent_titles: list = None, profile: dict = None) -> dict:
        scenario = get_scenario(format_id)
        if not scenario:
            raise ValueError(f"Format {format_id} không tồn tại")

        topic_id = brief.get("topic_id", "dynamic_research")
        profile_id = profile.get("id") if profile else None
        memory = self.writing_memory.get(profile_id, topic_id) if profile_id else None

        research_block = self._build_research_block(brief)
        topic = {
            "name": brief.get("topic_description", "Research-based Post")[:80],
            "description": brief.get("summary") or brief.get("topic_description", ""),
            "keywords": brief.get("key_insights", [])[:3],
        }
        
        prompt = self._build_prompt(scenario, topic, research_block=research_block, 
                                   recent_titles=recent_titles, memory=memory, profile=profile)
        return self._generate_with_retry(prompt, format_id, scenario, topic, recent_titles, research_block, profile=profile)

    def _generate_with_retry(self, prompt: str, format_id: str, scenario: dict, topic: dict, 
                             recent_titles: list, research_block: str = "", profile: dict = None) -> dict:
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                raw = self._call_llm(prompt)
                content = self._parse_json(raw, format_id)
                violations = self._validate_content(content)
                
                if violations:
                    logger.warning(f"[Attempt {attempt}] Brand rule violations: {violations}. Retry...")
                    if attempt == max_retries:
                        raise RuntimeError(f"Vi phạm brand rules sau nhiều lần thử: {violations}")
                    
                    # Rework prompt with feedback
                    prompt = self._build_prompt(scenario, topic, research_block=research_block,
                                               violation_hint=violations, recent_titles=recent_titles,
                                               profile=profile)
                    time.sleep(1)
                    continue
                
                return content
            except Exception as e:
                if attempt == max_retries:
                    raise e
                logger.warning(f"Attempt {attempt} fail: {e}")
                time.sleep(1)
        return {}

    def _build_prompt(
        self,
        scenario: dict,
        topic: dict,
        research_block: str = "",
        violation_hint: list = None,
        recent_titles: list = None,
        memory: dict = None,
        profile: dict = None,
    ) -> str:
        # Pillar 1 & 2: Dynamic branding & memory
        p_cfg = profile or {}
        
        # Website & Branding (Pillar 1)
        # Nếu thiếu thì để trống, AI tự quyết định không chèn if empty
        website = p_cfg.get("website", "")
        brand_name = p_cfg.get("brand_name", "")
        tagline = p_cfg.get("tagline", "")
        
        # Hashtags: profile specific or auto-generated
        p_hashtags = p_cfg.get("hashtags", [])
        if p_hashtags:
            fixed_hashtags = " ".join(f"#{h.lstrip('#')}" for h in p_hashtags)
            hashtag_instruction = f"Bắt buộc dùng các hashtags này: {fixed_hashtags}. Có thể thêm hashtags tự động liên quan."
        else:
            hashtag_instruction = "Tự động phát sinh các hashtags liên quan đến chủ đề."

        brand_vars = {
            "brand_rules": BRAND_RULES,
            "brand_name": brand_name or "Tổ chức/Chuyên gia (ẩn danh)",
            "brand_tagline": tagline or "",
            "brand_hashtag": "", # Sẽ được xử lý qua hashtag_instruction
            "blog_url": website or "N/A",
            "website": website or "N/A",
        }
        
        # Branding meta-instruction
        branding_meta = f"\n━━━ THÔNG TIN THƯƠNG HIỆU ━━━\n"
        if brand_name: branding_meta += f"- Tên: {brand_name}\n"
        if tagline:   branding_meta += f"- Tagline: {tagline}\n"
        if website:   branding_meta += f"- Website/URL: {website}\n"
        branding_meta += f"- Hashtags: {hashtag_instruction}\n"
        if not website:
            branding_meta += "- LƯU Ý: Không có website cụ thể, đừng chèn link rác hoặc link giả định vào CTA.\n"

        base = scenario["prompt"].format(**brand_vars)
        prompt = base.format(
            topic_name=topic.get("name", ""),
            topic_description=topic.get("description", ""),
            keywords=", ".join(topic.get("keywords", [])),
        )
        
        # Thêm meta branding vào đầu hoặc cuối prompt tùy scenario
        prompt = branding_meta + prompt

        # Inject Writing Memory (Pillar 2 Learning)
        if memory:
            memory_block = []
            if memory.get("approved_samples"):
                samples_text = "\n".join([f"SAMPLE:\nTitle: {s['title']}\nBody: {s['body']}\n---" 
                                        for s in memory["approved_samples"][:3]])
                memory_block.append(f"\n\n━━━ MẪU BÀI VIẾT ĐÃ ĐƯỢC CHẤP NHẬN (Hãy viết tương tự phong cách này):\n{samples_text}")
            
            if memory.get("learned_rules"):
                rules_text = "\n".join([f"- {r}" for r in memory["learned_rules"]])
                memory_block.append(f"\n\n━━━ CÁC QUY TẮC ĐÃ HỌC ĐƯỢC TỪ FEEDBACK NGƯỜI DÙNG (Bắt buộc tuân thủ):\n{rules_text}")
                
            if memory_block:
                prompt += "".join(memory_block)

        if research_block:
            inject = (
                f"\n\n--- NGUỔN NGHIÊN CỨU (dùng để làm giàu nội dung) ---\n"
                f"{research_block}\n"
                f"--- HẾẾT NGUỔN NGHIÊN CỨU ---\n"
            )
            if "Trả về JSON" in prompt:
                prompt = prompt.replace("Trả về JSON", inject + "\nTrả về JSON", 1)
            else:
                prompt += inject

        if recent_titles:
            titles_str = "\n".join(f"  - {t}" for t in recent_titles[:5])
            prompt += (
                f"\n\n⚠️ CÁC BÀI VỪA ĐĂNG GẦN ĐÂY (KHÔNG lặp lại góc nhìn, chủ đề, hook tương tự):\n"
                f"{titles_str}\n"
                f"Chọn góc tiếp cận KHÁC BIỆT hoàn toàn so với danh sách trên."
            )

        if violation_hint:
            violations_str = "\n".join(f"  - {v}" for v in violation_hint)
            prompt += f"\n\n⚠️ LẦN TRƯỚC BỊ REJECT VÌ VI PHẠM BRAND RULES:\n{violations_str}\nViết lại — KHÔNG được mắc lại các lỗi trên."

        return prompt

    def _call_llm(self, prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent"
        headers = {"x-goog-api-key": self.api_key}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
            }
        }
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        try:
            return data['candidates'][0]['content']['parts'][0]['text']
        except (KeyError, IndexError):
            raise ValueError(f"Cấu trúc phản hồi Gemini không đúng: {data}")

    def _parse_json(self, raw: str, format_id: str) -> dict:
        cleaned = raw.strip()
        match = re.search(r"```json\s*(.*?)\s*```", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1)
        else:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                cleaned = match.group(0)

        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"JSON Error. Raw: {raw[:500]}...")
            raise e

        required = REQUIRED_KEYS.get(format_id, [])
        missing = [k for k in required if k not in result]
        if missing:
            logger.warning(f"[{format_id}] LLM thiếu keys: {missing}")
        return result

    def _build_research_block(self, brief: dict) -> str:
        parts = []
        if brief.get("key_insights"):
            parts.append("Key insights:\n" + "\n".join(f"- {i}" for i in brief["key_insights"]))
        if brief.get("notable_stats"):
            parts.append("Stats:\n" + "\n".join(f"- {s}" for s in brief["notable_stats"]))
        if brief.get("content_angles"):
            parts.append("Angles:\n" + "\n".join(f"- {a}" for a in brief["content_angles"]))
        
        for item in brief.get("web_excerpts", [])[:2]:
            parts.append(f"Excerpt [{item['title']}]: {item['excerpt'][:400]}")
        
        return "\n\n".join(parts)

    def generate_custom_prompt(self, prompt: str) -> str:
        """Call Gemini trực tiếp cho meta-tasks."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent"
        headers = {"x-goog-api-key": self.api_key}
        payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.1}}
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            return ""

    def list_topics(self) -> list:
        return list(self._topics.values())
