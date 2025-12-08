import google.generativeai as genai
import streamlit as st
import json
import re
import time
from google.api_core.exceptions import ResourceExhausted
from pypinyin import pinyin, Style 

class Translator:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        # --- BẢO MẬT TUYỆT ĐỐI ---
        # Không dán Key ở đây. Code sẽ tự mò vào Két sắt (st.secrets) để lấy.
        try:
            # Ưu tiên Gemini 2.5 Pro
            self.model = genai.GenerativeModel('gemini-2.5-pro')
            self.model_name = "gemini-2.5-pro"
        except Exception:
            try:
                # Trượt về Gemini 2.5 Flash
                self.model = genai.GenerativeModel('gemini-2.5-flash')
                self.model_name = "gemini-2.5-flash"
            except Exception:
                # Trượt về Gemini-Pro (Dự phòng)
                self.model = genai.GenerativeModel('gemini-pro')
                self.model_name = "gemini-pro"

    def _run_gemini_safe(self, prompt, is_json=False):
        if not self.model: return None
        for i in range(3):
            try:
                # Thêm safety_settings để AI không từ chối dịch các văn bản lạ
                safety_settings = [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                ]
                response = self.model.generate_content(prompt, safety_settings=safety_settings)
                
                if is_json:
                    json_str = response.text.strip()
                    if "```" in json_str:
                        json_str = re.sub(r'```json|```', '', json_str).strip()
                    return json.loads(json_str)
                return response.text
            except ResourceExhausted: 
                time.sleep(5) 
            except Exception as e:
                # Nếu lỗi, chờ xíu rồi thử lại
                time.sleep(2)
                continue
        return None

    def translate_text(self, text, source_lang_code, target_lang_code, include_english):
        """Dịch chuẩn"""
        # Cache key
        cache_key = f"{text}_fix_{source_lang_code}_{target_lang_code}_{include_english}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]
        
        # Map tên ngôn ngữ
        lang_map = {v: k for k, v in st.session_state.get('languages', {}).items()}
        target_lang_name = lang_map.get(target_lang_code, target_lang_code)
        source_lang_name = lang_map.get(source_lang_code, source_lang_code)
        
        # Logic dịch kèm tiếng Anh (Chỉ dùng nếu nguồn và đích đều KHÔNG phải Anh)
        should_ask_english = include_english and target_lang_code != 'en' and source_lang_code != 'en'
        
        # --- PROMPT MỚI: CHẤP NHẬN VĂN BẢN LỖI ---
        base_prompt = f"""
        Act as a professional translator. 
        Target Language: {target_lang_name}.
        
        INPUT TEXT (May contain formatting errors, Typos, or merged words like 'THEORYOF'):
        "{text}"
        
        TASK:
        1. Fix any spacing/typo errors in your mind (e.g., "LOGICOF" -> "LOGIC OF").
        2. Translate the corrected meaning into {target_lang_name}.
        3. Maintain the original structure (Chapter numbers, lists).
        """

        if should_ask_english:
            base_prompt += f"""
            \nOUTPUT FORMAT:
            Line 1: {target_lang_name} translation.
            Line 2: English correction.
            """
        else:
            base_prompt += f"""
            \nOUTPUT FORMAT:
            Return ONLY the {target_lang_name} translation. No explanations.
            """
        
        # Gọi Gemini
        translation = self._run_gemini_safe(base_prompt)
        
        # Nếu AI vẫn trả về rỗng (hiếm), trả về thông báo để debug
        if not translation:
            return f"[AI không dịch được đoạn này: {text[:20]}...]"
            
        self.translated_words[cache_key] = translation
        return translation

    def process_chinese_text(self, word, target_lang_code):
        """Phân tích từ (Interactive Mode)"""
        # 1. Pinyin
        pinyin_text = ""
        try:
            pinyin_list = pinyin(word, style=Style.TONE)[0][0]
            pinyin_text = ' '.join(pinyin_list)
        except: pass
        
        # 2. Cache
        cache_key = f"{word}_int_{target_lang_code}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]
        
        # 3. Prompt
        lang_map = {v: k for k, v in st.session_state.get('languages', {}).items()}
        target_lang_name = lang_map.get(target_lang_code, target_lang_code)

        prompt = f"""
        Analyze word: "{word}". Target: {target_lang_name}.
        Return JSON ARRAY: [{{ "word": "{word}", "translations": ["Meaning"] }}]
        """
        
        data = self._run_gemini_safe(prompt, is_json=True)
        if data and isinstance(data, list) and len(data) > 0:
            result = {
                'word': word,
                'pinyin': pinyin_text,
                'translations': data[0].get('translations', [])
            }
            self.translated_words[cache_key] = [result]
            return [result]
        
        return [{'word': word, 'pinyin': pinyin_text, 'translations': ['...']}]
