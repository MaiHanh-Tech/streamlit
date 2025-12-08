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
        # --- BẢO MẬT TUYỆT ĐỐI ---
        # Không dán Key ở đây. Code sẽ tự mò vào Két sắt (st.secrets) để lấy.
        try:
            # Ưu tiên Gemini 2.5 Pro
            self.model = genai.GenerativeModel('gemini-2.5-pro')
            self.model_name = "gemini-2.5-pro"
        except Exception:
            try:
                # Trượt về Gemini 2.5 Flash
                self.model = genai.GenerativeModel('gemini-2.5-flash')
                self.model_name = "gemini-2.5-flash"
                
            except Exception:
                # Trượt về Gemini-Pro (Dự phòng)
                self.model = genai.GenerativeModel('gemini-pro')
                self.model_name = "gemini-pro"
                        
            except Exception as e:
                # st.error(f"Lỗi cấu hình API: {str(e)}")
                self.model = None
                
            self.translated_words = {} 
            self.initialized = True

    def _run_gemini_safe(self, prompt, is_json=False):
        if not self.model: return None
        
        # CẤU HÌNH TẮT BỘ LỌC KIỂM DUYỆT (QUAN TRỌNG NHẤT)
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        for i in range(3):
            try:
                response = self.model.generate_content(prompt, safety_settings=safety_settings)
                
                # Kiểm tra nếu bị chặn (Blocked)
                if response.prompt_feedback and response.prompt_feedback.block_reason:
                    print(f"Blocked: {response.prompt_feedback.block_reason}")
                    return None
                
                text_res = response.text
                
                if is_json:
                    if "```" in text_res:
                        text_res = re.sub(r'```json|```', '', text_res).strip()
                    try:
                        return json.loads(text_res)
                    except:
                        return None # Lỗi JSON thì trả về None để chuyển sang dịch thô
                        
                return text_res

            except ResourceExhausted: 
                time.sleep(5) 
            except InvalidArgument:
                # Lỗi này thường do văn bản quá nhạy cảm hoặc sai model
                return None 
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(1)
                continue
        return None

    def translate_text(self, text, source_lang_code, target_lang_code, include_english):
        """
        DỊCH CHUẨN - CHIẾN THUẬT: NẾU JSON HỎNG, CHUYỂN SANG DỊCH THẲNG (TEXT)
        """
        # Cache key
        cache_key = f"{text}_vPolitic_{source_lang_code}_{target_lang_code}_{include_english}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]
        
        # Map tên ngôn ngữ
        lang_map = {v: k for k, v in st.session_state.get('languages', {}).items()}
        target_name = lang_map.get(target_lang_code, target_lang_code)
        
        should_ask_english = include_english and target_lang_code != 'en' and source_lang_code != 'en'
        
        # --- CHIẾN THUẬT 1: THỬ DÙNG JSON (Để đẹp) ---
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

        # --- CHIẾN THUẬT 2: DỊCH THÔ (FORCE TRANSLATE) ---
        # Nếu JSON thất bại (do văn bản chính trị phức tạp), ta dùng lệnh đơn giản nhất
        
        # Dịch sang ngôn ngữ đích
        prompt_plain = f"Translate this text to {target_name} directly. Do not explain. Text: \n{text}"
        res_target = self._run_gemini_safe(prompt_plain, is_json=False)
        
        if not res_target:
            return "[Nội dung bị chặn bởi bộ lọc an toàn của Google]"

        if should_ask_english:
            # Dịch thêm tiếng Anh nếu cần
            prompt_eng = f"Translate this text to English directly: \n{text}"
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
        cache_key = f"{word}_int_vPolitic_{target_lang_code}"
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
