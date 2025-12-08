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
                
                # Cố gắng dùng các đời Model mạnh nhất
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
                # Tắt bộ lọc an toàn
                safety = [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                ]
                
                # Ép trả về JSON nếu cần (Gemini hỗ trợ response_mime_type nhưng dùng prompt cho an toàn mọi phiên bản)
                response = self.model.generate_content(prompt, safety_settings=safety)
                
                text_res = response.text
                
                if is_json:
                    # Lọc lấy phần JSON
                    if "```" in text_res:
                        text_res = re.sub(r'```json|```', '', text_res).strip()
                    # Tìm điểm bắt đầu { và kết thúc }
                    start = text_res.find('{')
                    end = text_res.rfind('}') + 1
                    if start != -1 and end != -1:
                        return json.loads(text_res[start:end])
                    return json.loads(text_res)
                    
                return text_res
            except ResourceExhausted: 
                time.sleep(5) 
            except Exception:
                time.sleep(2)
                continue
        return None

    def translate_text(self, text, source_lang_code, target_lang_code, include_english):
        """
        DỊCH CHUẨN - PHIÊN BẢN 'KỶ LUẬT SẮT'
        Sử dụng JSON Mode để ép AI không được trả về văn bản gốc.
        """
        
        # Cache key
        cache_key = f"{text}_force_json_{source_lang_code}_{target_lang_code}_{include_english}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]
        
        # Map tên ngôn ngữ
        lang_map = {v: k for k, v in st.session_state.get('languages', {}).items()}
        target_lang_name = lang_map.get(target_lang_code, target_lang_code)
        source_lang_name = lang_map.get(source_lang_code, source_lang_code)
        
        # Logic dịch kèm tiếng Anh
        should_ask_english = include_english and target_lang_code != 'en' and source_lang_code != 'en'
        
        # --- PROMPT ÉP JSON ---
        prompt = f"""
        You are a translation API. 
        Task: Translate the text from {source_lang_name} to {target_lang_name}.
        
        INPUT TEXT (Ignore OCR errors/typos like 'suchas', 'needed . y'):
        "{text}"
        
        INSTRUCTIONS:
        1. Fix formatting errors internally.
        2. Translate the MEANING to {target_lang_name}.
        3. RETURN JSON ONLY. NO MARKDOWN. NO EXPLANATIONS.
        """

        if should_ask_english:
            prompt += f"""
            JSON FORMAT:
            {{
                "target_text": "Put {target_lang_name} translation here",
                "english_text": "Put corrected English text here"
            }}
            """
        else:
            prompt += f"""
            JSON FORMAT:
            {{
                "target_text": "Put {target_lang_name} translation here"
            }}
            """
        
        # Gọi Gemini với chế độ JSON
        data = self._run_gemini_safe(prompt, is_json=True)
        
        if data and isinstance(data, dict):
            target_val = data.get("target_text", "")
            
            # Kiểm tra xem AI có 'lừa' mình trả lại tiếng Anh không
            # Nếu đích là Việt mà kết quả không có dấu tiếng Việt -> Dịch lại
            if target_lang_code == 'vi' and target_val and len(target_val) > 10:
                vietnamese_chars = "àáảãạăắằẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"
                has_vn_sign = any(c in target_val for c in vietnamese_chars)
                if not has_vn_sign and "PREFACE" not in text: # Preface có thể dịch là Loi noi dau (khong dau) nhung hiem
                     # Fallback dịch thô
                     return self._translate_fallback(text, target_lang_name)

            if should_ask_english:
                english_val = data.get("english_text", text)
                result = f"{target_val}\n{english_val}"
            else:
                result = target_val
            
            self.translated_words[cache_key] = result
            return result
            
        return "[Error: AI did not return valid JSON translation]"

    def _translate_fallback(self, text, target_lang_name):
        """Phương án B: Dịch thẳng thừng nếu JSON thất bại"""
        prompt = f"Translate this strictly to {target_lang_name}: {text}"
        return self._run_gemini_safe(prompt)

    def process_chinese_text(self, word, target_lang_code):
        # (Giữ nguyên logic cũ)
        pinyin_text = ""
        try:
            pinyin_list = pinyin(word, style=Style.TONE)[0][0]
            pinyin_text = ' '.join(pinyin_list)
        except: pass
        
        cache_key = f"{word}_int_v3_{target_lang_code}"
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
