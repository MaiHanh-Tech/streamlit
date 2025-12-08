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
                
                # --- TUÂN THỦ YÊU CẦU: DÙNG 2.5 PRO / FLASH ---
                try:
                    self.model = genai.GenerativeModel('gemini-2.5-pro')
                except:
                    try:
                        self.model = genai.GenerativeModel('gemini-2.5-flash')
                    except:
                        # Fallback cuối cùng nếu Key chưa được cấp quyền 2.5
                        self.model = genai.GenerativeModel('gemini-1.5-pro')
                        
            except Exception as e:
                self.model = None
            
            self.translated_words = {} 
            self.initialized = True

    def _run_gemini_safe(self, prompt, is_json=False):
        if not self.model: return None
        
        # TẮT TOÀN BỘ BỘ LỌC AN TOÀN (Bắt buộc cho văn bản chính trị)
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        for i in range(3):
            try:
                response = self.model.generate_content(prompt, safety_settings=safety_settings)
                
                # Nếu bị chặn (Blocked) -> Trả về None để hàm gọi biết đường xử lý
                if response.prompt_feedback and response.prompt_feedback.block_reason:
                    return None
                
                text_res = response.text
                
                if is_json:
                    if "```" in text_res:
                        text_res = re.sub(r'```json|```', '', text_res).strip()
                    try:
                        return json.loads(text_res)
                    except:
                        return None # Lỗi JSON thì trả về None
                        
                return text_res

            except ResourceExhausted: 
                time.sleep(5) 
            except Exception:
                time.sleep(1)
                continue
        return None

    def translate_text(self, text, source_lang_code, target_lang_code, include_english):
        """
        DỊCH CHUẨN: Ưu tiên JSON -> Nếu lỗi/bị chặn -> Chuyển sang Text thường
        """
        # Cache key
        cache_key = f"{text}_v2.5_{source_lang_code}_{target_lang_code}_{include_english}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]
        
        # Map tên ngôn ngữ
        lang_map = {v: k for k, v in st.session_state.get('languages', {}).items()}
        target_name = lang_map.get(target_lang_code, target_lang_code)
        
        should_ask_english = include_english and target_lang_code != 'en' and source_lang_code != 'en'
        
        # --- CÁCH 1: DÙNG JSON (ĐỂ ĐỊNH DẠNG ĐẸP) ---
        prompt_json = f"""
        Translate the following text to {target_name}.
        Input: "{text}"
        Instruction: Accurate translation. Return JSON ONLY.
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

        # --- CÁCH 2: DỊCH THẲNG (NẾU CÁCH 1 BỊ CHẶN HOẶC LỖI) ---
        # Văn bản chính trị thường bị lỗi JSON, nên phải có bước này
        prompt_plain = f"Translate this text to {target_name} immediately. No explanation. Text: \n{text}"
        res_target = self._run_gemini_safe(prompt_plain, is_json=False)
        
        if not res_target:
            # Nếu vẫn không được -> Có thể do Model quá nhạy cảm -> Thử lại lần cuối với prompt cực ngắn
            res_target = self._run_gemini_safe(f"Translate to {target_name}: {text}", is_json=False)

        if not res_target:
            return "[Lỗi: Google AI từ chối dịch đoạn này do nội dung nhạy cảm]"

        if should_ask_english:
            # Dịch thêm tiếng Anh nếu cần (Gọi lần 2)
            prompt_eng = f"Translate this text to English immediately: \n{text}"
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
        cache_key = f"{word}_int_v2.5_{target_lang_code}"
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
