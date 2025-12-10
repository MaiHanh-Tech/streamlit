import streamlit as st
import jieba
from pypinyin import pinyin, Style
from openai import OpenAI
from pydantic import BaseModel, Field, SecretStr
from typing import Optional, List, Dict, Any

# Map từ mã ISO (vi, en) sang tên đầy đủ
CODE_TO_LANG_NAME = {
    "ar": "Arabic",
    "en": "English",
    "fr": "French",
    "id": "Indonesian",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "fa": "Persian",
    "pt": "Portuguese",
    "ru": "Russian",
    "es": "Spanish",
    "th": "Thai",
    "uz": "Uzbek",
    "vi": "Vietnamese",
    "zh": "Chinese",
    "zh-Hans": "Chinese (Simplified)"
}

class DeepSeekConfig(BaseModel):
    api_key: SecretStr
    base_url: str = Field(default="https://api.deepseek.com")
    model: str = Field(default="deepseek-chat")

class TranslationWord(BaseModel):
    word: str
    pinyin: str
    translations: List[str]

class Translator:
    def __init__(self):
        # Luôn khởi tạo lại config mỗi khi tạo object mới
        self._init_config()
        self.translated_words: Dict[str, str] = {}

    def _init_config(self):
        try:
            # Ưu tiên lấy từ mục [deepseek], nếu không có thì fallback sang azure cũ (để tránh crash)
            secrets = st.secrets.get("deepseek", {})
            api_key = secrets.get("api_key") or st.secrets.get("azure_translator", {}).get("key", "")
            
            self.config = DeepSeekConfig(
                api_key=api_key,
                base_url=secrets.get("base_url", "https://api.deepseek.com"),
                model=secrets.get("model", "deepseek-chat")
            )
            
            self.client = OpenAI(
                api_key=self.config.api_key.get_secret_value(),
                base_url=self.config.base_url
            )
        except Exception as e:
            print(f"Config Error: {e}")
            self.client = None

    def translate_text(self, text: str, target_lang: str) -> str:
        """Translate text using DeepSeek API"""
        if not text or not text.strip():
            return ""

        # Lấy tên ngôn ngữ đầy đủ
        full_lang_name = CODE_TO_LANG_NAME.get(target_lang, target_lang)
        cache_key = f"{text}_{full_lang_name}"
        
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]

        if not self.client:
            return "[Error: API Key missing or Client not initialized]"

        try:
            system_prompt = (
                f"You are a professional translator. Translate the following Chinese text into {full_lang_name}. "
                "Output ONLY the translated text. Do not include pinyin, notes, or explanations."
            )

            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.1,
                stream=False
            )

            translation = response.choices[0].message.content.strip()
            
            if translation:
                self.translated_words[cache_key] = translation
                return translation
            
            return "[Error: Empty response from AI]"

        except Exception as e:
            error_msg = f"[Error: {str(e)}]"
            print(f"DeepSeek API Error: {error_msg}")
            return error_msg

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
                
                # Luôn đảm bảo cấu trúc trả về đúng
                processed_words.append({
                    'word': word,
                    'pinyin': word_pinyin if is_meaningful else "",
                    'translations': [translation] if translation else []
                })
            
            return processed_words
            
        except Exception as e:
            print(f"Word Processing Error: {str(e)}")
            return []
