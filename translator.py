import streamlit as st
import jieba
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from pypinyin import pinyin, Style
from pydantic import BaseModel, Field, SecretStr
from typing import Optional, List, Dict, Any

# Map từ mã ISO sang tên đầy đủ (Gemini thích tên đầy đủ)
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
                 # Cấu hình Gemini
            genai.configure(api_key=self.config.api_key.get_secret_value())
            
            # Cấu hình Model & Safety Settings (Tắt chặn để dịch thoải mái hơn)
            self.model = genai.GenerativeModel(
                model_name=self.config.model,
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                }
            )
            self.is_ready = True
        except Exception as e:
            print(f"Gemini Config Error: {e}")
            self.is_ready = False
            

    def translate_text(self, text: str, target_lang: str) -> str:
        """Translate text using Google Gemini API"""
        if not text or not text.strip():
            return ""

        # Lấy tên ngôn ngữ
        full_lang_name = CODE_TO_LANG_NAME.get(target_lang, target_lang)
        cache_key = f"{text}_{full_lang_name}"
        
        # Check cache
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
            # Xử lý các lỗi thường gặp của Gemini
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
                
                try:
                    if word.strip():
                        char_pinyins = [pinyin(char, style=Style.TONE)[0][0] for char in word]
                        word_pinyin = ' '.join(char_pinyins)
                except Exception:
                    pass

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
