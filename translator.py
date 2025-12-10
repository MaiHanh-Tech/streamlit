import streamlit as st
import jieba
import time
from pypinyin import pinyin, Style
from openai import OpenAI
from pydantic import BaseModel, Field, SecretStr
from typing import Optional, List, Dict, Any

# --- Constants: Language Code Mapping ---
# Map từ mã ISO (vi, en) sang tên đầy đủ để AI hiểu rõ hơn
CODE_TO_LANG_NAME = {
    "en": "English",
    "vi": "Vietnamese",
    "zh": "Chinese",
    "zh-Hans": "Chinese (Simplified)"
}

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
            
            # Fallback cho trường hợp người dùng cũ
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

        # Lấy tên ngôn ngữ đầy đủ (ví dụ: 'vi' -> 'Vietnamese')
        # Nếu không tìm thấy thì giữ nguyên mã
        full_lang_name = CODE_TO_LANG_NAME.get(target_lang, target_lang)

        # Check cache
        cache_key = f"{text}_{full_lang_name}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]

        if not self.client:
            print("Error: OpenAI Client not initialized (Check API Key)")
            return ""

        try:
            # Prompt được tối ưu hóa: Chỉ định rõ ngôn ngữ nguồn và đích bằng tên đầy đủ
            system_prompt = (
                f"You are a professional translator. Translate the following Chinese text into {full_lang_name}. "
                "Output ONLY the translated text. Do not include pinyin, notes, or explanations."
            )

            # Gọi API
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.1,  # Nhiệt độ thấp để dịch sát nghĩa, ít sáng tạo linh tinh
                stream=False
            )

            translation = response.choices[0].message.content.strip()
            
            # Kiểm tra nếu AI trả về chính text gốc (dịch thất bại)
            if translation == text:
                 print(f"Warning: DeepSeek returned original text for '{text}'")

            if translation:
                self.translated_words[cache_key] = translation
                # In ra console để debug xem nó dịch ra gì
                # print(f"Translated: {text[:10]}... -> {translation[:10]}... ({full_lang_name})") 
                return translation
            
            return ""

        except Exception as e:
            # In lỗi chi tiết ra console/terminal để chị dễ debug
            print(f"DeepSeek API Error for text '{text[:10]}...': {str(e)}")
            return ""

    def process_chinese_text(self, text: str, target_lang: str = "en") -> List[Dict[str, Any]]:
        """
        Process Chinese text for word-by-word translation.
        """
        try:
            words = list(jieba.cut(text))
            processed_words = []
            
            # Chuyển đổi mã ngôn ngữ sang tên đầy đủ cho phần word-by-word
            full_lang_name = CODE_TO_LANG_NAME.get(target_lang, target_lang)

            for i, word in enumerate(words):
                is_meaningful = '\u4e00' <= word <= '\u9fff'
                word_pinyin = ""
                translation = ""
                
                # 1. Pinyin
                try:
                    if word.strip():
                        char_pinyins = [pinyin(char, style=Style.TONE)[0][0] for char in word]
                        word_pinyin = ' '.join(char_pinyins)
                except Exception:
                    pass

                # 2. Translation
                if is_meaningful:
                    translation = self.translate_text(word, target_lang) # translate_text sẽ tự handle mapping ngôn ngữ
                
                try:
                    word_obj = TranslationWord(
                        word=word,
                        pinyin=word_pinyin if is_meaningful else "",
                        translations=[translation] if translation else []
                    )
                    processed_words.append(word_obj.model_dump())
                except Exception as e:
                    processed_words.append({
                        'word': word,
                        'pinyin': '',
                        'translations': []
                    })
            
            return processed_words
            
        except Exception as e:
            print(f"Error processing text: {str(e)}")
            return []
