import google.generativeai as genai
import streamlit as st
import json
import re
import uuid
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
                    json_str = response.text.strip().replace("```json", "").replace("```", "")
                    return json.loads(json_str)
                return response.text
            except ResourceExhausted: 
                time.sleep(5)
            except Exception as e:
                return None
        return None

    def translate_text(self, text, source_lang, target_lang, include_english): # <--- ĐÃ SỬA
        """Dịch cả đoạn văn (Standard Translation)"""
        cache_key = f"{text}_std_{source_lang}_{target_lang}_{include_english}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]
        
        target_lang_name = st.session_state.get('languages', {}).get(target_lang, target_lang)
        source_lang_name = st.session_state.get('languages', {}).get(source_lang, source_lang)
        
        # Thêm yêu cầu dịch sang Anh
        english_req = "Dịch thêm sang Tiếng Anh." if include_english and target_lang != 'en' else ""

        prompt = f"""
        Act as a professional book translator.
        Translate the following text from {source_lang_name} to {target_lang_name}. {english_req}
        
        Text: "{text}"
        
        YÊU CẦU ĐỊNH DẠNG:
        1. Bản dịch chính thức ({target_lang_name}) nằm ở dòng đầu tiên.
        2. Nếu có yêu cầu dịch thêm, bản dịch phụ (Tiếng Anh) nằm ở dòng thứ hai.
        """
        translation = self._run_gemini_safe(prompt)
        
        if translation:
            self.translated_words[cache_key] = translation
        return translation or ""

    def process_chinese_text(self, word, target_lang):
        """
        Phân tích từng từ (Interactive Mode)
        LƯU Ý: Chế độ này chỉ hoạt động tốt khi SOURCE là TIẾNG TRUNG
        """
        
        # 1. Get Pinyin (Vẫn phải dùng Pinyin vì đây là App gốc)
        pinyin_text = ""
        try:
            pinyin_list = pinyin(word, style=Style.TONE)[0][0]
            pinyin_text = ' '.join(pinyin_list)
        except: pass
        
        # 2. Get Translations (Dùng Gemini)
        cache_key = f"{word}_int_{target_lang}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]
        
        target_lang_name = st.session_state.get('languages', {}).get(target_lang, target_lang)

        prompt = f"""
        Phân tích từ Tiếng Trung: "{word}"
        
        YÊU CẦU: Dịch sang Tiếng Việt và Tiếng Anh. 
        Trả về kết quả ở định dạng JSON ARRAY. Mỗi object có key: 'translations'.
        
        Ví dụ: [{{ "word": "中", "pinyin": "zhōng", "translations": ["Giữa", "Center"]}}]
        """
        
        translations_data = self._run_gemini_safe(prompt, is_json=True)
        
        if translations_data and len(translations_data) > 0:
            result = {
                'word': word,
                'pinyin': pinyin_text,
                'translations': translations_data[0].get('translations', [])
            }
            self.translated_words[cache_key] = [result]
            return [result]
        
        return [{
            'word': word,
            'pinyin': pinyin_text,
            'translations': ['Lỗi dịch thuật (AI Error)']
        }]
