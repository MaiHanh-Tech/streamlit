import google.generativeai as genai
import streamlit as st
import json
import time
import jieba
from pypinyin import pinyin, Style
from google.api_core.exceptions import ResourceExhausted

class Translator:
    def __init__(self):
        try:
            api_key = st.secrets["api_keys"]["gemini_api_key"]
            genai.configure(api_key=api_key)
            # Dùng Flash cho nhanh vì ta sẽ gọi nhiều lần
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        except:
            self.model = None
        self.translated_words = {} 

    def _call_ai_raw(self, prompt):
        """Hàm gọi AI thô sơ nhất, tắt hết bộ lọc"""
        if not self.model: return None
        
        # Tắt sạch bộ lọc
        safety = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        
        for i in range(3):
            try:
                response = self.model.generate_content(prompt, safety_settings=safety)
                if response.text:
                    return response.text.strip()
            except ResourceExhausted:
                time.sleep(2)
            except Exception:
                time.sleep(1)
        return None

    def translate_text(self, text, source_lang, target_lang, include_english):
        """
        DỊCH RIÊNG LẺ TỪNG NGÔN NGỮ ĐỂ ĐẢM BẢO KHÔNG MẤT CHỮ
        """
        cache_key = f"{text}_brute_{source_lang}_{target_lang}_{include_english}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]

        # Map tên ngôn ngữ
        lang_map = {v: k for k, v in st.session_state.get('languages', {}).items()}
        target_name = lang_map.get(target_lang, target_lang)
        source_name = lang_map.get(source_lang, source_lang)

        # 1. DỊCH SANG NGÔN NGỮ ĐÍCH (VD: VIỆT)
        # Prompt cực đơn giản để AI không hiểu nhầm
        prompt_main = f"Translate the following text from {source_name} to {target_name}: \n{text}"
        res_main = self._call_ai_raw(prompt_main)
        
        if not res_main:
            # Fallback nếu AI từ chối: Trả về chính nó (để không bị Error)
            res_main = text 

        # 2. DỊCH SANG TIẾNG ANH (NẾU CẦN)
        res_eng = ""
        if include_english and target_lang != 'en' and source_lang != 'en':
            prompt_eng = f"Translate the following text from {source_name} to English: \n{text}"
            res_eng = self._call_ai_raw(prompt_eng)
            if not res_eng: res_eng = "..."

        # 3. GHÉP KẾT QUẢ
        if res_eng:
            final_res = f"{res_main}\n{res_eng}"
        else:
            final_res = res_main

        self.translated_words[cache_key] = final_res
        return final_res

    def process_chinese_text(self, word, target_lang):
        # (Giữ nguyên logic cũ cho phần Interactive)
        pinyin_text = ""
        try:
            pinyin_list = pinyin(word, style=Style.TONE)[0][0]
            pinyin_text = ' '.join(pinyin_list)
        except: pass
        
        lang_map = {v: k for k, v in st.session_state.get('languages', {}).items()}
        target_name = lang_map.get(target_lang, target_lang)
        
        # Dùng hàm thô để lấy nghĩa
        prompt = f"Translate Chinese word '{word}' to {target_name}. Just the meaning."
        meaning = self._call_ai_raw(prompt)
        
        return [{
            'word': word,
            'pinyin': pinyin_text,
            'translations': [meaning if meaning else "..."]
        }]
