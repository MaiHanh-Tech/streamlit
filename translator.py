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
                try:
                    self.model = genai.GenerativeModel('gemini-2.5-pro')
                except:
                    self.model = genai.GenerativeModel('gemini-2.5-flash')
            except Exception as e:
                st.error(f"Lỗi cấu hình API Gemini: {str(e)}")
                self.model = None
            self.translated_words = {}
            self.initialized = True

    def _run_gemini_safe(self, prompt, is_json=False):
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

    def translate_text(self, text, source_lang_code, target_lang_code, include_english):
        """Dịch cả đoạn văn với PROMPT CHUYÊN GIA CAO CẤP"""
        
        # Cache key
        cache_key = f"{text}_expert_{source_lang_code}_{target_lang_code}_{include_english}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]
        
        # Map tên ngôn ngữ
        lang_map = {v: k for k, v in st.session_state.get('languages', {}).items()}
        target_lang_name = lang_map.get(target_lang_code, target_lang_code)
        source_lang_name = lang_map.get(source_lang_code, source_lang_code)
        
        # Logic dịch kèm tiếng Anh
        should_ask_english = include_english and target_lang_code != 'en' and source_lang_code != 'en'
        
        # --- PROMPT "CHUYÊN GIA" CỦA CHỊ ---
        base_prompt = f"""
        Bạn là một chuyên gia dịch thuật có nhiều kinh nghiệm trong việc chuyển ngữ các văn bản phức tạp.
        Hãy phân tích và dịch tài liệu dưới đây từ **{source_lang_name}** sang **{target_lang_name}** với độ chính xác cao.
        
        TIÊU CHUẨN DỊCH THUẬT:
        1. **Tinh thần & Văn phong:** Đảm bảo giữ nguyên tinh thần, ý nghĩa, văn phong và sắc thái ngữ nghĩa của tác giả.
        2. **Thuật ngữ chuyên ngành:** Dịch phù hợp với ngữ cảnh và cung cấp ghi chú giải thích nếu cần.
        3. **Điển tích & Thành ngữ:** Tìm cách chuyển tải phù hợp với văn hóa của ngôn ngữ đích ({target_lang_name}) mà vẫn giữ được tinh thần nguyên bản.
        4. **Từ đa nghĩa:** Chọn từ ngữ mượt mà nhất, bỏ bớt từ thừa/lặp.
        5. **Cấu trúc:** Giữ nguyên cấu trúc của tài liệu gốc (tiêu đề, đoạn văn, danh sách...).
        """

        # Yêu cầu định dạng đầu ra (để code Python cắt được dòng)
        if should_ask_english:
            base_prompt += f"""
            \nĐỊNH DẠNG ĐẦU RA (BẮT BUỘC):
            - Dòng 1: Bản dịch {target_lang_name} (Theo tiêu chuẩn chuyên gia ở trên).
            - Dòng 2: Bản dịch Tiếng Anh.
            - KHÔNG thêm lời dẫn, KHÔNG trích dẫn lại câu hỏi.
            """
        else:
            base_prompt += f"""
            \nĐỊNH DẠNG ĐẦU RA (BẮT BUỘC):
            - Chỉ cung cấp bản dịch {target_lang_name} (Theo tiêu chuẩn chuyên gia ở trên).
            - KHÔNG trích dẫn, KHÔNG giải thích thêm.
            """

        base_prompt += f"""
        \nTOÀN BỘ NỘI DUNG ĐƯỢC CUNG CẤP SAU ĐÂY:
        "{text}"
        """
        
        # Gọi Gemini
        translation = self._run_gemini_safe(base_prompt)
        
        if translation:
            self.translated_words[cache_key] = translation
        return translation or ""

    def process_chinese_text(self, word, target_lang_code):
        """Phân tích từ (Interactive Mode)"""
        # Giữ nguyên logic cũ
        pinyin_text = ""
        try:
            pinyin_list = pinyin(word, style=Style.TONE)[0][0]
            pinyin_text = ' '.join(pinyin_list)
        except: pass
        
        cache_key = f"{word}_int_{target_lang_code}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]
        
        lang_map = {v: k for k, v in st.session_state.get('languages', {}).items()}
        target_lang_name = lang_map.get(target_lang_code, target_lang_code)

        prompt = f"""
        Analyze this word: "{word}"
        Target Language: {target_lang_name}
        Return JSON ARRAY with key 'translations'. 
        """
        
        data = self._run_gemini_safe(prompt, is_json=True)
        if data:
            result = {
                'word': word,
                'pinyin': pinyin_text,
                'translations': data[0].get('translations', [])
            }
            self.translated_words[cache_key] = [result]
            return [result]
        
        return [{'word': word, 'pinyin': pinyin_text, 'translations': ['Error']}]
