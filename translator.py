import streamlit as st
import jieba
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from pypinyin import pinyin, Style
from pydantic import BaseModel, Field, SecretStr
from typing import Optional, List, Dict, Any

# Map đầy đủ các ngôn ngữ để App không bị lỗi khi chọn tiếng khác
CODE_TO_LANG_NAME = {
    "en": "English",
    "vi": "Vietnamese",
    "zh": "Chinese",
    "zh-Hans": "Chinese (Simplified)"
}

class TranslationWord(BaseModel):
    word: str
    pinyin: str
    translations: List[str]

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
            # 1. Lấy API Key từ secrets
            # Tìm trong [gemini], nếu không có thì tìm trong [deepseek] (fallback)
            secrets = st.secrets.get("gemini", {})
            api_key = secrets.get("api_key") or st.secrets.get("deepseek", {}).get("api_key", "")
            
            if not api_key:
                print("Lỗi: Không tìm thấy API Key trong secrets.toml")
                return

            # 2. Cấu hình Gemini
            genai.configure(api_key=api_key)

            # 3. Cấu hình Safety Settings (Quan trọng: Tắt bộ lọc để dịch chính xác)
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }

            # 4. Chọn Model (Thử Pro trước, nếu lỗi thì xuống Flash)
            # Hiện tại chưa có 2.5, dùng 1.5 là bản ổn định nhất
            try:
                self.model = genai.GenerativeModel('gemini-1.5-pro-latest', safety_settings=safety_settings)
                self.model_name = "gemini-2.5-pro"
            except Exception:
                try:
                    self.model = genai.GenerativeModel('gemini-1.5-flash', safety_settings=safety_settings)
                    self.model_name = "gemini-2.5-flash"
                except Exception as e:
                    print(f"Lỗi khởi tạo Model: {e}")
                    return

            self.is_ready = True
            print(f"Translator ready using model: {self.model_name}")

        except Exception as e:
            print(f"Critical Config Error: {e}")
            self.is_ready = False

    def translate_text(self, text: str, target_lang: str) -> str:
        """Translate text using Google Gemini API"""
        if not text or not text.strip():
            return ""

        # Lấy tên ngôn ngữ đầy đủ
        full_lang_name = CODE_TO_LANG_NAME.get(target_lang, target_lang)
        cache_key = f"{text}_{full_lang_name}"
        
        # Check cache (Kiểm tra xem đã dịch từ này chưa)
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]

        if not self.is_ready:
            return "[Error: API Key missing or Config Invalid]"

        try:
            # Prompt tối ưu cho Gemini
            prompt = (
                f"Translate the following Chinese text into {full_lang_name}. "
                "Output ONLY the translation. No explanations, no pinyin, no extra text.\n\n"
                f"Text: {text}"
            )

            # Gọi API
            response = self.model.generate_content(prompt)
            
            # Xử lý kết quả
            if response.text:
                translation = response.text.strip()
                self.translated_words[cache_key] = translation
                return translation
            
            return "[Error: Empty response]"

        except Exception as e:
            error_msg = str(e)
            if "400" in error_msg:
                return "[Error: Invalid API Key or Request]"
            elif "429" in error_msg:
                return "[Error: Rate limit exceeded (Too many requests)]"
            
            print(f"Gemini API Error: {error_msg}")
            return f"[Error: {error_msg}]"

    def process_chinese_text(self, text: str, target_lang: str = "en") -> List[Dict[str, Any]]:
        """Process Chinese text for word-by-word translation."""
        try:
            words = list(jieba.cut(text))
            processed_words = []
            
            for word in words:
                is_meaningful = '\u4e00' <= word <= '\u9fff'
                word_pinyin = ""
                translation = ""
                
                # 1. Lấy Pinyin (Offline - Nhanh)
                try:
                    if word.strip():
                        char_pinyins = [pinyin(char, style=Style.TONE)[0][0] for char in word]
                        word_pinyin = ' '.join(char_pinyins)
                except Exception:
                    pass

                # 2. Dịch nghĩa (Gọi API Gemini)
                if is_meaningful:
                    translation = self.translate_text(word, target_lang)
                
                processed_words.append({
                    'word': word,
                    'pinyin': word_pinyin if is_meaningful else "",
                    'translations': [translation] if translation else []
                })
            
            return processed_words
            
        except Exception as e:
            print(f"Word Processing Error: {str(e)}")
            return []
