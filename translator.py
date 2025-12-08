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
                
                # --- CHỐT HẠ: DÙNG GEMINI 1.5 FLASH (ỔN ĐỊNH NHẤT) ---
                # Model 2.5 hiện tại chưa public rộng rãi API, dùng sẽ bị lỗi ngầm
                self.model = genai.GenerativeModel('gemini-1.5-flash')
                        
            except Exception as e:
                self.model = None
            
            self.translated_words = {} 
            self.initialized = True

    def _run_gemini_safe(self, prompt, is_json=False):
        if not self.model: return None
        
        # TẮT BỘ LỌC AN TOÀN TUYỆT ĐỐI
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        
        # Cấu hình sinh văn bản để tránh bị cắt cụt
        generation_config = genai.types.GenerationConfig(
            candidate_count=1,
            max_output_tokens=2048,
            temperature=0.3, # Giảm sáng tạo để dịch chính xác hơn
        )

        for i in range(3):
            try:
                response = self.model.generate_content(
                    prompt, 
                    safety_settings=safety_settings,
                    generation_config=generation_config
                )
                
                if not response.parts:
                    return None
                
                text_res = response.text
                
                if is_json:
                    if "```" in text_res:
                        text_res = re.sub(r'```json|```', '', text_res).strip()
                    try:
                        return json.loads(text_res)
                    except:
                        return None 
                        
                return text_res

            except ResourceExhausted: 
                time.sleep(5) 
            except Exception as e:
                # Nếu model hiện tại lỗi, thử lại sau 1s
                time.sleep(1)
                continue
        return None

    def translate_text(self, text, source_lang_code, target_lang_code, include_english):
        # Cache key
        cache_key = f"{text}_stable_{source_lang_code}_{target_lang_code}_{include_english}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]
        
        # Map tên ngôn ngữ
        lang_map = {v: k for k, v in st.session_state.get('languages', {}).items()}
        target_name = lang_map.get(target_lang_code, target_lang_code)
        
        should_ask_english = include_english and target_lang_code != 'en' and source_lang_code != 'en'
        
        # --- CHIẾN THUẬT 1: JSON ---
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

        # --- CHIẾN THUẬT 2: DỊCH THÔ (CỨU CÁNH CUỐI CÙNG) ---
        # Prompt đơn giản nhất có thể để AI không bị confuse
        prompt_plain = f"Translate this to {target_name}: {text}"
        res_target = self._run_gemini_safe(prompt_plain, is_json=False)
        
        if not res_target:
            return f"[Lỗi kết nối AI. Vui lòng thử lại đoạn ngắn hơn]"

        if should_ask_english:
            prompt_eng = f"Translate this to English: {text}"
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
        pinyin_text = ""
        try:
            pinyin_list = pinyin(word, style=Style.TONE)[0][0]
            pinyin_text = ' '.join(pinyin_list)
        except: pass
        
        cache_key = f"{word}_int_stable_{target_lang_code}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]
        
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
