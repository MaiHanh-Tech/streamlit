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
                # Lấy API Key
                api_key = st.secrets["api_keys"]["gemini_api_key"]
                genai.configure(api_key=api_key)
                
                # Cấu hình Model
                try:
                    self.model = genai.GenerativeModel('gemini-1.5-flash')
                except:
                    self.model = genai.GenerativeModel('gemini-pro')
                        
            except Exception as e:
                st.error(f"Lỗi cấu hình API: {str(e)}")
                self.model = None
                
            self.translated_words = {} 
            self.initialized = True

    def _run_gemini_safe(self, prompt, is_json=False):
        if not self.model:
            return None
            
        for i in range(3):
            try:
                # Tắt bộ lọc an toàn
                safety = [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                ]
                
                response = self.model.generate_content(prompt, safety_settings=safety)
                text_res = response.text
                
                if is_json:
                    # Làm sạch JSON
                    if "```" in text_res:
                        text_res = re.sub(r'```json|```', '', text_res).strip()
                    try:
                        return json.loads(text_res)
                    except:
                        return None
                        
                return text_res
            except ResourceExhausted: 
                time.sleep(5) 
            except Exception:
                time.sleep(2)
                continue
        return None

    def translate_text(self, text, source_lang_code, target_lang_code, include_english):
        # Cache key
        cache_key = f"{text}_v5_{source_lang_code}_{target_lang_code}_{include_english}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]
        
        # Map tên ngôn ngữ
        lang_map = {v: k for k, v in st.session_state.get('languages', {}).items()}
        target_name = lang_map.get(target_lang_code, target_lang_code)
        source_name = lang_map.get(source_lang_code, source_lang_code)
        
        should_ask_english = include_english and target_lang_code != 'en' and source_lang_code != 'en'
        
        # --- PROMPT ---
        prompt = f"""
        Translate the following text from {source_name} to {target_name}.
        Input: "{text}"
        
        Instructions:
        1. Ignore OCR errors/typos.
        2. Translate meaning accurately.
        3. RETURN JSON ONLY.
        """

        if should_ask_english:
            prompt += f"""
            JSON Format: {{ "target_text": "Translation in {target_name}", "english_text": "Translation in English" }}
            """
        else:
            prompt += f"""
            JSON Format: {{ "target_text": "Translation in {target_name}" }}
            """
        
        # Gọi Gemini (Lớp 1 - JSON)
        data = self._run_gemini_safe(prompt, is_json=True)
        
        if data and isinstance(data, dict):
            target_val = data.get("target_text", "")
            if target_val:
                if should_ask_english:
                    eng_val = data.get("english_text", "")
                    result = f"{target_val}\n{eng_val}"
                else:
                    result = target_val
                
                self.translated_words[cache_key] = result
                return result

        # --- FALLBACK (Lớp 2 - Dịch thô) ---
        fallback_prompt = f"Translate this text to {target_name} immediately: {text}"
        fallback_res = self._run_gemini_safe(fallback_prompt, is_json=False)
        
        if fallback_res:
            self.translated_words[cache_key] = fallback_res
            return fallback_res

        return "[Lỗi: AI không phản hồi]"

    def process_chinese_text(self, word, target_lang_code):
        # 1. Pinyin
        pinyin_text = ""
        try:
            pinyin_list = pinyin(word, style=Style.TONE)[0][0]
            pinyin_text = ' '.join(pinyin_list)
        except:
            pass
        
        # 2. Cache
        cache_key = f"{word}_int_v5_{target_lang_code}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]
        
        # 3. Prompt
        lang_map = {v: k for k, v in st.session_state.get('languages', {}).items()}
        target_name = lang_map.get(target_lang_code, target_lang_code)

        prompt = f"""
        Analyze word: "{word}". Target: {target_name}.
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
