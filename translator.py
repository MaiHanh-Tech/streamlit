import google.generativeai as genai
import streamlit as st
import json
import time
import jieba
import re
from pypinyin import pinyin, Style 
from google.api_core.exceptions import ResourceExhausted

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
                
                # Cấu hình Model
                try:
                    self.model = genai.GenerativeModel('gemini-1.5-flash')
                except:
                    self.model = genai.GenerativeModel('gemini-pro')
                        
            except Exception as e:
                self.model = None
            
            self.translated_words = {} 
            self.initialized = True

    def _run_gemini(self, prompt):
        if not self.model: return None
        
        # Tắt bộ lọc an toàn (để dịch văn bản chính trị)
        safety = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        
        for i in range(3):
            try:
                response = self.model.generate_content(prompt, safety_settings=safety)
                text = response.text.strip()
                return text
            except ResourceExhausted: 
                time.sleep(2)
            except Exception:
                time.sleep(1)
        return None

    def translate_text(self, text, target_lang, include_english):
        """Dịch đoạn văn Tiếng Trung (Vẫn dùng JSON/Text để không mất cấu trúc)"""
        cache_key = f"{text}_{target_lang}_{include_english}"
        if cache_key in self.translated_words: return self.translated_words[cache_key]
        
        # Tạo Prompt đơn giản để tránh lỗi
        prompt = f"""
        Translate this Chinese text to {target_lang}.
        Input: "{text}"
        """
        
        if include_english and target_lang != 'en':
            prompt += f"""
            Output JSON format: 
            {{ 
                "target": "Translation in {target_lang}", 
                "english": "Translation in English" 
            }}
            """
        else:
            prompt += f"""
            Output ONLY the translation in {target_lang}.
            """
            
        data = self._run_gemini(prompt)
        
        # Xử lý kết quả trả về
        if data:
            try:
                # Cố gắng đọc JSON
                json_data = json.loads(data)
                if include_english and target_lang != 'en':
                    res = f"{json_data.get('target', '')}\n{json_data.get('english', '')}"
                else:
                    res = json_data.get('target', '')
                
                self.translated_words[cache_key] = res
                return res
            except Exception:
                # FALLBACK: Nếu lỗi JSON, trả về nguyên văn bản dịch thô (Không bị Error)
                self.translated_words[cache_key] = data
                return data
            
        return "[Error translating]"

    def process_chinese_text(self, word, target_lang):
        """Phân tích từ vựng (Interactive)"""
        pinyin_text = ""
        try:
            pinyin_list = pinyin(word, style=Style.TONE)[0][0]
            pinyin_text = ' '.join(pinyin_list)
        except: pass
        
        prompt = f"""
        Analyze Chinese word: "{word}". Target: {target_lang}.
        Output JSON: [{{ "word": "{word}", "translations": ["Meaning 1"] }}]
        """
        
        res = self._run_gemini(prompt)
        try:
            data = json.loads(res)
            return [{
                'word': word,
                'pinyin': pinyin_text,
                'translations': data[0].get('translations', [])
            }]
        except:
            return [{'word': word, 'pinyin': pinyin_text, 'translations': ['...']}]

