mport google.generativeai as genai
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
                
                # Cấu hình Model: Flash xử lý văn bản dài tốt hơn
                try:
                    self.model = genai.GenerativeModel('gemini-1.5-flash')
                except:
                    self.model = genai.GenerativeModel('gemini-pro')
                        
            except Exception as e:
                st.error(f"Lỗi cấu hình API Gemini: {str(e)}")
                self.model = None
                
            self.translated_words = {} 
            self.initialized = True

    def _run_gemini_safe(self, prompt, is_json=False):
        if not self.model: return None
        for i in range(3):
            try:
                # Tắt bộ lọc an toàn để không bị chặn nội dung chính trị/y khoa
                safety = [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                ]
                
                response = self.model.generate_content(prompt, safety_settings=safety)
                text_res = response.text
                
                if is_json:
                    # Cố gắng làm sạch JSON
                    if "```" in text_res:
                        text_res = re.sub(r'```json|```', '', text_res).strip()
                    try:
                        return json.loads(text_res)
                    except json.JSONDecodeError:
                        # Nếu lỗi JSON, trả về None để kích hoạt Fallback
                        return None
                        
                return text_res
            except ResourceExhausted: 
                time.sleep(5) 
            except Exception:
                time.sleep(2)
                continue
        return None

    def translate_text(self, text, source_lang_code, target_lang_code, include_english):
        """
        DỊCH CHUẨN - CƠ CHẾ BẢO HIỂM 2 LỚP
        """
        # Cache key
        cache_key = f"{text}_v4_{source_lang_code}_{target_lang_code}_{include_english}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]
        
        # Map tên ngôn ngữ
        lang_map = {v: k for k, v in st.session_state.get('languages', {}).items()}
        target_lang_name = lang_map.get(target_lang_code, target_lang_code)
        source_lang_name = lang_map.get(source_lang_code, source_lang_code)
        
        should_ask_english = include_english and target_lang_code != 'en' and source_lang_code != 'en'
        
        # --- LỚP 1: THỬ DÙNG JSON (ĐỂ CÓ CẤU TRÚC ĐẸP) ---
        prompt_json = f"""
        Translate the following text from {source_lang_name} to {target_lang_name}.
        Input: "{text}"
        
        Requirements:
        1. Keep the meaning accurate.
        2. Keep the formatting (1. 2. 3...).
        3. RETURN JSON ONLY.
        """

        if should_ask_english:
            prompt_json += f"""
            JSON Format: {{ "target_text": "...", "english_text": "..." }}
            """
        else:
            prompt_json += f"""
            JSON Format: {{ "target_text": "..." }}
            """
        
        data = self._run_gemini_safe(prompt_json, is_json=True)
        
        # Nếu Lớp 1 thành công
        if data and isinstance(data, dict):
            target_val = data.get("target_text", "")
            if target_val:
                if should_ask_english:
                    english_val = data.get("english_text", "")
                    result = f"{target_val}\n{english_val}"
                else:
                    result = target_val
                
                self.translated_words[cache_key] = result
                return result

        # --- LỚP 2: FALLBACK (DỊCH THÔ - NẾU JSON THẤT BẠI) ---
        # Đây là phần cứu cánh cho đoạn văn chị vừa gửi
        fallback_prompt = f"""
        Translate this text directly from {source_lang_name} to {target_lang_name}.
        Do not explain. Just translate.
        
        Text: "{text}"
        """
        
        # Gọi dịch thô
        fallback_res = self._run_gemini_safe(fallback_prompt, is_json=False)
        
        if fallback_res:
            # Nếu cần tiếng Anh mà fallback chỉ trả về 1 cục, ta gọi thêm 1 lần nữa cho tiếng Anh
            if should_ask_english:
                eng_prompt = f"Translate this to English: {text}"
                eng_res = self._run_gemini_safe(eng_prompt, is_json=False)
                final_res = f"{fallback_res}\n{eng_res}"
                self.translated_words[cache_key] = final_res
                return final_res
            else:
                self.translated_words[cache_key] = fallback_res
                return fallback_res

        return "[Lỗi: AI không phản hồi]"

    def process_chinese_text(self, word, target_lang_code):
        # (Giữ nguyên logic cũ)
        pinyin_text = ""
        try:
            pinyin_list = pinyin(word, style=Style.TONE)[0][0]
            pinyin_text = ' '.join(pinyin_list)
        except: pass
        
        cache_key = f"{word}_int_v4_{target_lang_code}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]
        
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
