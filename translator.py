import streamlit as st
import jieba
import time
from pypinyin import pinyin, Style
from openai import OpenAI
from pydantic import BaseModel, Field, SecretStr
from typing import Optional, List, Dict, Any

# --- Pydantic Models for Configuration & Data ---

class DeepSeekConfig(BaseModel):
    api_key: SecretStr
    base_url: str = Field(default="https://api.deepseek.com")
    model: str = Field(default="deepseek-chat")

class TranslationWord(BaseModel):
    word: str
    pinyin: str
    translations: List[str]

# --- Translator Class ---

class Translator:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if not self.initialized:
            self._init_config()
            self.translated_words: Dict[str, str] = {}
            self.initialized = True

    def _init_config(self):
        """Initialize DeepSeek configuration using Pydantic"""
        try:
            # Lấy config từ secrets.toml
            secrets = st.secrets.get("deepseek", {})
            
            # Fallback cho trường hợp người dùng cũ vẫn để tên key là azure_translator nhưng muốn dùng deepseek
            # Hoặc tạo config mới
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
            print(f"Configuration Error: {str(e)}")
            self.client = None

    def translate_text(self, text: str, target_lang: str) -> str:
        """Translate text using DeepSeek API"""
        if not text or not text.strip():
            return ""

        # Check cache
        cache_key = f"{text}_{target_lang}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]

        if not self.client:
            return "[Config Error]"

        try:
            # Tạo prompt cho DeepSeek
            # System prompt định hướng hành vi dịch thuật chính xác
            system_prompt = (
                f"You are a professional translator. Translate the following Chinese text into {target_lang}. "
                "Output ONLY the translated text, no explanations, no pinyin, no extra notes."
            )

            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.3, # Giảm temperature để dịch chính xác hơn
                stream=False
            )

            translation = response.choices[0].message.content.strip()
            
            # Update cache
            if translation:
                self.translated_words[cache_key] = translation
                return translation
            
            return ""

        except Exception as e:
            print(f"DeepSeek Translation error: {str(e)}")
            # Fallback hoặc return rỗng
            return ""

    def process_chinese_text(self, text: str, target_lang: str = "en") -> List[Dict[str, Any]]:
        """
        Process Chinese text for word-by-word translation.
        Retains Jieba for consistent segmentation behavior with the UI.
        """
        try:
            # Segment the text using jieba
            words = list(jieba.cut(text))
            
            processed_words = []
            
            for i, word in enumerate(words):
                # Skip processing for basic punctuation/numbers/whitespace to save tokens
                is_meaningful = '\u4e00' <= word <= '\u9fff'
                
                word_pinyin = ""
                translation = ""
                
                # 1. Get Pinyin (Local processing - Fast)
                try:
                    if word.strip():
                        char_pinyins = [pinyin(char, style=Style.TONE)[0][0] for char in word]
                        word_pinyin = ' '.join(char_pinyins)
                except Exception:
                    pass

                # 2. Get Translation (API Call)
                if is_meaningful:
                    # Check cache first inside translate_text
                    translation = self.translate_text(word, target_lang)
                
                # Construct result
                # Using Pydantic model for internal validation then converting to dict for app compatibility
                try:
                    word_obj = TranslationWord(
                        word=word,
                        pinyin=word_pinyin if is_meaningful else "",
                        translations=[translation] if translation else []
                    )
                    processed_words.append(word_obj.model_dump())
                except Exception as e:
                    # Fallback for structure error
                    processed_words.append({
                        'word': word,
                        'pinyin': '',
                        'translations': []
                    })
            
            return processed_words
            
        except Exception as e:
            print(f"Error processing text: {str(e)}")
            return []
