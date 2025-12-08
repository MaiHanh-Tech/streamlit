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
                
                # Cấu hình Model
                try:
                    self.model = genai.GenerativeModel('gemini-2.5-pro')
                except:
                    try:
                        self.model = genai.GenerativeModel('gemini-1.5-pro')
                    except:
                        self.model = genai.GenerativeModel('gemini-1.5-flash')
                        
            except Exception as e:
                st.error(f"Lỗi cấu hình API Gemini: {str(e)}")
                self.model = None
            self.translated_words = {}
            self.initialized = True

    def _run_gemini_safe(self, prompt, is_json=False):
        if not self.model: return None
        for i in range(3):
            try:
                # Tắt bộ lọc an toàn để không bị chặn văn bản y khoa/sinh học
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
                time.sleep(2)
                continue
        return None

    def translate_text(self, text, source_lang_code, target_lang_code, include_english):
        """Dịch chuẩn (Standard Translation)"""
        cache_key = f"{text}_fix3_{source_lang_code}_{target_lang_code}_{include_english}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]
        
        # Mapping tên ngôn ngữ thủ công để đảm bảo chính xác
        LANG_MAP = {
            'vi': 'Vietnamese', 'en': 'English', 'zh': 'Chinese', 'fr': 'French',
            'ja': 'Japanese', 'ko': 'Korean', 'ru': 'Russian', 'es': 'Spanish'
        }
        # Lấy tên từ session nếu không có trong map cứng
        target_name = LANG_MAP.get(target_lang_code, st.session_state.get('languages', {}).get(target_lang_code, target_lang_code))
        source_name = LANG_MAP.get(source_lang_code, st.session_state.get('languages', {}).get(source_lang_code, source_lang_code))
        
        should_ask_english = include_english and target_lang_code != 'en' and source_lang_code != 'en'
        
        # --- PROMPT KHẮC PHỤC LỖI "KHÔNG DỊCH" ---
        base_prompt = f"""
        ROLE: Professional Translator.
        SOURCE LANGUAGE: {source_name}.
        TARGET LANGUAGE: {target_name}.
        
        INPUT TEXT (May contain OCR errors like 'suchas', 'theoryof'):
        "{text}"
        
        INSTRUCTIONS:
        1. Ignore OCR errors/typos. Guess the correct meaning.
        2. TRANSLATE the meaning into **{target_name}**.
        3. DO NOT output {source_name} (unless requested).
        4. DO NOT explain the errors. Just translate.
        """

        if should_ask_english:
            base_prompt += f"""
            \nOUTPUT FORMAT (Strictly 2 lines):
            Line 1: {target_name} translation.
            Line 2: English text (Corrected version).
            """
        else:
            base_prompt += f"""
            \nOUTPUT FORMAT:
            Return ONLY the {target_name} translation.
            """
        
        translation = self._run_gemini_safe(base_prompt)
        
        # Kiểm tra nếu AI trả về y nguyên văn bản gốc (Lỗi thường gặp)
        if translation and translation.strip() == text.strip():
             # Thử lại lần 2 với prompt gắt hơn
             retry_prompt = f"Translate this to {target_name} immediately: {text}"
             translation = self._run_gemini_safe(retry_prompt)

        if translation:
            self.translated_words[cache_key] = translation
            return translation
            
        return f"..."

    def process_chinese_text(self, word, target_lang_code):
        # (Giữ nguyên phần này như cũ)
        pinyin_text = ""
        try:
            pinyin_list = pinyin(word, style=Style.TONE)[0][0]
            pinyin_text = ' '.join(pinyin_list)
        except: pass
        
        cache_key = f"{word}_int_v2_{target_lang_code}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]
        
        target_name = st.session_state.get('languages', {}).get(target_lang_code, target_lang_code)

        prompt = f"""
        Analyze word: "{word}". Target: {target_name}.
        Return JSON ARRAY: [{{ "word": "{word}", "translations": ["Meaning in {target_name}"] }}]
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
