import streamlit as st
import jieba
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from pypinyin import pinyin, Style
import time
import random
from typing import List, Dict, Any

# Map tên ngôn ngữ đầy đủ để Gemini hiểu rõ hơn
CODE_TO_LANG_NAME = {
    "en": "English",
    "vi": "Vietnamese",
    "zh": "Chinese",
    "zh-Hans": "Chinese (Simplified)"
}

class Translator:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if not self.initialized:
            self.translated_words: Dict[str, str] = {}
            self.is_ready = False
            self._init_config()
            self.initialized = True

    def _init_config(self):
        try:
            # 1. Lấy API Key từ secrets (ưu tiên [gemini], fallback [deepseek])
            secrets = st.secrets.get("gemini", {})
            api_key = secrets.get("api_key") or st.secrets.get("deepseek", {}).get("api_key", "")
            
            if not api_key:
                print("Error: API Key not found in secrets.toml")
                return

            # 2. Cấu hình Gemini
            genai.configure(api_key=api_key)

            # 3. Cấu hình Safety Settings (Tắt bộ lọc để dịch không bị chặn)
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]

            # 4. Chọn Model: gemini-1.5-flash (Nhanh, Rẻ, Ổn định)
            self.model_name = "gemini-2.5-flash"
            self.model = genai.GenerativeModel(
                model_name=self.model_name,
                safety_settings=safety_settings
            )

            self.is_ready = True
            print(f"Translator Ready: Using {self.model_name}")

        except Exception as e:
            print(f"Gemini Config Error: {str(e)}")
            self.is_ready = False

    def translate_text(self, text: str, target_lang: str) -> str:
        """Translate text using Google Gemini API with Retry Logic"""
        if not text or not text.strip():
            return ""

        # Lấy tên đầy đủ của ngôn ngữ (VD: vi -> Vietnamese)
        full_lang_name = CODE_TO_LANG_NAME.get(target_lang, target_lang)
        cache_key = f"{text}_{full_lang_name}"
        
        # Check cache first
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]

        if not self.is_ready:
            return "[Error: Config Invalid]"
        
        # --- CƠ CHẾ RETRY (Xử lý lỗi 429 Rate Limit) ---
        max_retries = 5
        base_delay = 2 

        prompt = (
            f"Translate the following Chinese text into {full_lang_name}. "
            "Output ONLY the translation. No explanations, no pinyin.\n\n"
            f"Text: {text}"
        )

        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(prompt)
                
                if response.text:
                    translation = response.text.strip()
                    self.translated_words[cache_key] = translation
                    return translation
                return ""

            except Exception as e:
                error_msg = str(e)
                # Nếu bị quá tải (429), chờ và thử lại
                if "429" in error_msg:
                    if attempt < max_retries - 1:
                        wait_time = base_delay * (2 ** attempt) + random.uniform(0, 1)
                        print(f"Rate limit (429). Retrying in {wait_time:.2f}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        return "[Error: Rate limit exceeded]"
                
                # Các lỗi khác
                print(f"Translation Error: {error_msg}")
                if "404" in error_msg: return "[Error: Model not found]"
                if "400" in error_msg: return "[Error: Invalid API Key]"
                return f"[Error: {error_msg}]"
        
        return "[Error: Request Failed]"

    def process_chinese_text(self, text, target_lang="en"):
        """Process Chinese text for word-by-word translation"""
        try:
            # Segment the text using jieba
            words = list(jieba.cut(text))
            processed_words = []
            
            for i, word in enumerate(words):
                is_meaningful = '\u4e00' <= word <= '\u9fff'
                word_pinyin = ""
                translation = ""

                # 1. Get Pinyin
                try:
                    if word.strip():
                        char_pinyins = [pinyin(char, style=Style.TONE)[0][0] for char in word]
                        word_pinyin = ' '.join(char_pinyins)
                except Exception:
                    pass

                # 2. Get Translation
                if is_meaningful:
                    # Thêm delay nhỏ để tránh spam API khi chạy vòng lặp
                    time.sleep(0.2)
                    translation = self.translate_text(word, target_lang)

                processed_words.append({
                    'word': word,
                    'pinyin': word_pinyin if is_meaningful else "",
                    'translations': [translation] if translation else []
                })
            
            return processed_words
            
        except Exception as e:
            print(f"Error processing text: {str(e)}")
            return []
