import google.generativeai as genai
import streamlit as st
import json
import re
import time
from google.api_core.exceptions import ResourceExhausted, InvalidArgument
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
                
                # --- CẤU HÌNH MODEL: ƯU TIÊN HÀNG MỚI NHẤT ---
                # Thử lần lượt các đời model mới nhất
                models_to_try = [
                    'gemini-2.5-pro', 
                    'gemini-2.5-flash',
                    'gemini-2.0-flash-exp', # Bản experimental mới nhất hiện nay
                    'gemini-1.5-pro',
                    'gemini-1.5-flash'
                ]
                
                self.model = None
                for m in models_to_try:
                    try:
                        self.model = genai.GenerativeModel(m)
                        # Test thử kết nối nhẹ
                        self.model.generate_content("Hi")
                        print(f"Connected to {m}")
                        break
                    except:
                        continue
                        
            except Exception as e:
                self.model = None
            
            self.translated_words = {} 
            self.initialized = True

    def _run_gemini_safe(self, prompt, is_json=False):
        if not self.model: return None
        
        # CẤU HÌNH TẮT CHẶT BỘ LỌC AN TOÀN (BẮT BUỘC CHO VĂN BẢN CHÍNH TRỊ)
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        for i in range(3):
            try:
                response = self.model.generate_content(prompt, safety_settings=safety_settings)
                
                # Kiểm tra nếu bị chặn hoàn toàn
                if not response.parts:
                    if response.prompt_feedback and response.prompt_feedback.block_reason:
                        print(f"Blocked reason: {response.prompt_feedback.block_reason}")
                        return None
                
                text_res = response.text
                
                if is_json:
                    # Làm sạch JSON cực mạnh
                    if "```" in text_res:
                        text_res = re.sub(r'```json|```', '', text_res).strip()
                    try:
                        return json.loads(text_res)
                    except:
                        return None # Lỗi JSON -> Trả None để kích hoạt Fallback
                        
                return text_res

            except ResourceExhausted: 
                time.sleep(5) 
            except Exception as e:
                # Các lỗi khác (như 500, Safety...)
                time.sleep(1)
                continue
        return None

    def translate_text(self, text, source_lang_code, target_lang_code, include_english):
        """
        DỊCH VĂN BẢN CHÍNH TRỊ/PHỨC TẠP
        Chiến thuật: Thử JSON -> Nếu thất bại -> Dịch Thô (Plain Text)
        """
        cache_key = f"{text}_final_{source_lang_code}_{target_lang_code}_{include_english}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]
        
        # Map tên ngôn ngữ
        lang_map = {v: k for k, v in st.session_state.get('languages', {}).items()}
        target_name = lang_map.get(target_lang_code, target_lang_code)
        
        should_ask_english = include_english and target_lang_code != 'en' and source_lang_code != 'en'
        
        # --- CÁCH 1: DÙNG JSON (Ưu tiên) ---
        prompt_json = f"""
        Translate the following text to {target_name}.
        Text: "{text}"
        
        Instruction: 
        - Accurate translation. 
        - Maintain political/formal tone if present.
        - RETURN VALID JSON ONLY.
        """
        if should_ask_english:
            prompt_json += 'Format: {"target": "...", "english": "..."}'
        else:
            prompt_json += 'Format: {"target": "..."}'

        data = self._run_gemini_safe(prompt_json, is_json=True)
        
        if data and isinstance(data, dict):
            t_val = data.get("target", "")
            if t_val:
                if should_ask_english:
                    e_val = data.get("english", "")
                    res = f"{t_val}\n{e_val}"
                else:
                    res = t_val
                
                self.translated_words[cache_key] = res
                return res

        # --- CÁCH 2: DỊCH THÔ (CỨU CÁNH) ---
        # Nếu JSON hỏng (thường do văn bản chính trị quá dài), chuyển sang dịch thẳng
        prompt_plain = f"""
        Translate the text below to {target_name} immediately.
        Do not describe. Do not output markdown code blocks. Just the translation.
        
        Text:
        {text}
        """
        
        res_target = self._run_gemini_safe(prompt_plain, is_json=False)
        
        if not res_target:
            # Nếu vẫn không được, trả về thông báo lỗi cụ thể thay vì im lặng
            return "[Lỗi: Nội dung bị AI chặn do chính sách an toàn. Hãy thử chia nhỏ đoạn văn hơn.]"

        if should_ask_english:
            # Dịch thêm tiếng Anh
            prompt_eng = f"Translate the text below to English immediately:\n{text}"
            res_eng = self._run_gemini_safe(prompt_eng, is_json=False)
            if res_eng:
                final_res = f"{res_target}\n{res_eng}"
            else:
                final_res = res_target
        else:
            final_res = res_target

        self.translated_words[cache_key] = final_res
        return final_res

    def process_chinese_text(self, word, target_lang_code):
        # 1. Pinyin
        pinyin_text = ""
        try:
            pinyin_list = pinyin(word, style=Style.TONE)[0][0]
            pinyin_text = ' '.join(pinyin_list)
        except: pass
        
        # 2. Cache
        cache_key = f"{word}_int_final_{target_lang_code}"
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
