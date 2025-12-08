import google.generativeai as genai
import streamlit as st
import json
import re
import uuid
import time
from google.api_core.exceptions import ResourceExhausted
# Thư viện pypinyin (Nếu bị lỗi chị nhớ cài: pip install pypinyin)
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
            # --- Cấu hình GEMINI (Thay thế Azure) ---
            try:
                # Lấy API Key từ secrets
                api_key = st.secrets["api_keys"]["gemini_api_key"]
                genai.configure(api_key=api_key)
                
                # Ưu tiên Pro, trượt về Flash
                try:
                    self.model = genai.GenerativeModel('gemini-2.5-pro')
                except:
                    self.model = genai.GenerativeModel('gemini-2.5-flash')
                
            except Exception as e:
                st.error(f"Lỗi cấu hình API Gemini: {str(e)}")
                self.model = None
                
            self.translated_words = {} # Cache
            self.initialized = True

    def _run_gemini_safe(self, prompt, is_json=False):
        """Hàm gọi AI an toàn, chống lỗi Quota"""
        if not self.model: return None
        for i in range(3):
            try:
                response = self.model.generate_content(prompt)
                if is_json:
                    # Dọn dẹp JSON
                    json_str = response.text.strip().replace("```json", "").replace("```", "")
                    return json.loads(json_str)
                return response.text
            except ResourceExhausted: 
                time.sleep(5)
            except Exception as e:
                return None
        return None

    def translate_text(self, text, target_lang):
        """Dịch cả đoạn văn (Standard Translation) - Thay thế _call_azure_translate"""
        cache_key = f"{text}_std_{target_lang}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]
        
        # Lấy tên ngôn ngữ để Gemini hiểu
        target_lang_name = st.session_state.get('languages', {}).get(target_lang, target_lang)

        prompt = f"""
        Act as a professional book translator. Translate the Chinese text to {target_lang_name}.
        Text: "{text}"
        """
        translation = self._run_gemini_safe(prompt)
        
        if translation:
            self.translated_words[cache_key] = translation
        return translation or ""

    def process_chinese_text(self, word, target_lang):
        """Process Chinese word for word-by-word translation (Interactive)"""
        
        target_lang_name = st.session_state.get('languages', {}).get(target_lang, target_lang)
        
        # 1. Get Pinyin (Dùng pypinyin gốc)
        pinyin_text = ""
        try:
            pinyin_list = pinyin(word, style=Style.TONE)[0][0]
            pinyin_text = ' '.join(pinyin_list)
        except: pass
        
        # 2. Get Translations (Dùng Gemini)
        cache_key = f"{word}_int_{target_lang}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]
        
        prompt = f"""
        Phân tích từ Tiếng Trung sau cho người học.
        Từ: "{word}"
        
        YÊU CẦU: Dịch sang Tiếng Việt và Tiếng Anh (nếu không có yêu cầu đặc biệt). 
        Trả về kết quả ở định dạng JSON ARRAY. Mỗi object có key: 'translations'.
        
        Ví dụ: [{{ "word": "中", "pinyin": "zhōng", "translations": ["Giữa", "Center"]}}]
        """
        
        # Gọi AI lấy dịch nghĩa (translations)
        translations_data = self._run_gemini_safe(prompt, is_json=True)
        
        if translations_data and len(translations_data) > 0:
            result = {
                'word': word,
                'pinyin': pinyin_text,
                # Lấy translations từ kết quả JSON của AI
                'translations': translations_data[0].get('translations', [])
            }
            self.translated_words[cache_key] = [result] # Lưu cache dưới dạng list để tương thích
            return [result]
        
        # Trả về cấu trúc lỗi để App không sập
        return [{
            'word': word,
            'pinyin': pinyin_text,
            'translations': ['Lỗi dịch thuật (AI Error)']
        }]
