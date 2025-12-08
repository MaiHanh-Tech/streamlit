import google.generativeai as genai
import streamlit as st
import json
import re
import time
from google.api_core.exceptions import ResourceExhausted
from pypinyin import pinyin, Style 

class Translator:
    def __init__(self):
        try:
            api_key = st.secrets["api_keys"]["gemini_api_key"]
            genai.configure(api_key=api_key)
            try: self.model = genai.GenerativeModel('gemini-1.5-flash')
            except: self.model = genai.GenerativeModel('gemini-pro')
        except: self.model = None
        self.translated_words = {} 

    def _run_gemini(self, prompt):
        if not self.model: return None
        for i in range(3):
            try:
                # Ép trả về JSON
                response = self.model.generate_content(prompt + "\nRETURN JSON ONLY.")
                text = response.text.strip()
                if "```" in text: text = re.sub(r'```json|```', '', text).strip()
                return json.loads(text)
            except: time.sleep(2)
        return None

    def translate_text(self, text, target_lang, include_english):
        """Dịch đoạn văn Tiếng Trung"""
        cache_key = f"{text}_{target_lang}_{include_english}"
        if cache_key in self.translated_words: return self.translated_words[cache_key]
        
        target_name = st.session_state.languages.get(target_lang, target_lang) if 'languages' in st.session_state else target_lang
        
        # Prompt chuyên dụng cho Tiếng Trung
        prompt = f"""
        Translate this Chinese text to {target_name}.
        Input: "{text}"
        """
        
        if include_english and target_lang != 'en':
            prompt += f"""
            Output JSON format: 
            {{ 
                "target": "Translation in {target_name}", 
                "english": "Translation in English" 
            }}
            """
        else:
            prompt += f"""
            Output JSON format: {{ "target": "Translation in {target_name}" }}
            """
            
        data = self._run_gemini(prompt)
        
        if data:
            if include_english and target_lang != 'en':
                res = f"{data.get('target', '')}\n{data.get('english', '')}"
            else:
                res = data.get('target', '')
            
            self.translated_words[cache_key] = res
            return res
            
        return "[Error translating]"

    def process_chinese_text(self, word, target_lang):
        """Phân tích từ vựng (Interactive)"""
        pinyin_text = ""
        try:
            pinyin_list = pinyin(word, style=Style.TONE)[0][0]
            pinyin_text = ' '.join(pinyin_list)
        except: pass
        
        target_name = st.session_state.languages.get(target_lang, target_lang) if 'languages' in st.session_state else target_lang
        
        prompt = f"""
        Analyze Chinese word: "{word}". Target: {target_name}.
        Output JSON: [{{ "word": "{word}", "translations": ["Meaning 1", "Meaning 2"] }}]
        """
        
        data = self._run_gemini(prompt)
        if data and isinstance(data, list):
            result = {
                'word': word,
                'pinyin': pinyin_text,
                'translations': data[0].get('translations', [])
            }
            return [result]
            
        return [{'word': word, 'pinyin': pinyin_text, 'translations': ['...']}]
