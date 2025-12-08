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
        if not self.initialized:
            try:
                api_key = st.secrets["api_keys"]["gemini_api_key"]
                genai.configure(api_key=api_key)
                # Dùng Flash cho nhanh và ít bị từ chối
                self.model = genai.GenerativeModel('gemini-1.5-flash')
            except Exception as e:
                st.error(f"Lỗi cấu hình API Gemini: {str(e)}")
                self.model = None
            self.initialized = True

    def _run_gemini_safe(self, prompt, is_json=False):
        if not self.model: return None
        for i in range(3):
            try:
                # Tắt toàn bộ bộ lọc an toàn
                safety = [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                ]
                response = self.model.generate_content(prompt, safety_settings=safety)
                
                if is_json:
                    json_str = response.text.strip()
                    if "```" in json_str:
                        json_str = re.sub(r'```json|```', '', json_str).strip()
                    return json.loads(json_str)
                return response.text
            except ResourceExhausted: 
                time.sleep(5) 
            except Exception as e:
                time.sleep(1)
                continue
        return None

    def translate_text(self, text, source_lang_code, target_lang_code, include_english):
        """Dịch chuẩn (Standard Translation) - KHÔNG DÙNG CACHE ĐỂ FIX LỖI"""
        
        # Map tên ngôn ngữ
        lang_map = {v: k for k, v in st.session_state.get('languages', {}).items()}
        target_lang_name = lang_map.get(target_lang_code, target_lang_code)
        source_lang_name = lang_map.get(source_lang_code, source_lang_code)
        
        should_ask_english = include_english and target_lang_code != 'en' and source_lang_code != 'en'
        
        # --- KỸ THUẬT ONE-SHOT (Mớm lời) ---
        # Bắt AI nhìn ví dụ để hiểu nhiệm vụ
        
        example_input = "Hello world. This text has erors."
        example_output = "Xin chào thế giới. Văn bản này có lỗi." if target_lang_code == 'vi' else "Bonjour le monde..."
        
        prompt = f"""
        Translate the following text from {source_lang_name} to {target_lang_name}.
        
        [EXAMPLE]
        Input: "{example_input}"
        Output: "{example_output}"
        [END EXAMPLE]
        
        [REAL TASK]
        Input (May contain OCR errors/typos, ignore them and translate meaning): 
        "{text}"
        
        Output (Translate to {target_lang_name} ONLY):
        """

        if should_ask_english:
            prompt = f"""
            Translate from {source_lang_name} to {target_lang_name} AND English.
            
            Input: "{text}"
            
            Output Format:
            Line 1: {target_lang_name} translation.
            Line 2: English correction.
            """
        
        # Gọi Gemini
        translation = self._run_gemini_safe(prompt)
        
        # Nếu AI vẫn trả về tiếng Anh (nguyên văn), ta ép nó dịch lại lần 2
        # So sánh độ dài để đoán xem nó có copy nguyên văn không
        if translation and len(translation) > 0:
            # Nếu đích là Việt mà kết quả không có dấu tiếng Việt (cơ bản) -> Nghi ngờ lỗi
            if target_lang_code == 'vi' and not any(char in translation for char in "àáảãạăắằẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"):
                 # Gọi lại lần 2 với lệnh gắt hơn
                 retry_prompt = f"You failed. Translate this specific text to VIETNAMESE immediately: {text}"
                 translation = self._run_gemini_safe(retry_prompt)

        return translation if translation else "..."

    def process_chinese_text(self, word, target_lang_code):
        # (Giữ nguyên phần Pinyin)
        pinyin_text = ""
        try:
            pinyin_list = pinyin(word, style=Style.TONE)[0][0]
            pinyin_text = ' '.join(pinyin_list)
        except: pass
        
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
            return [result]
        
        return [{'word': word, 'pinyin': pinyin_text, 'translations': ['...']}]
