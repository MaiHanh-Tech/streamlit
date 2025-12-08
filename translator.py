import streamlit as st
import google.generativeai as genai
import time
from pypinyin import pinyin, Style
import jieba
from datetime import datetime
import plotly.graph_objects as go
from google.api_core.exceptions import ResourceExhausted

class Translator:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
        return cls._instance

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
                # Trượt về Gemini-Pro (Dự phòng)
                self.model = genai.GenerativeModel('gemini-pro')
                self.model_name = "gemini-pro"
                
            except Exception as e:
                print(f"Gemini Init Error: {str(e)}")
                self.model = None

            # Giữ nguyên Cache
            self.translated_words = {}
            self.initialized = True

    def translate_text(self, text, target_lang):
        """Translate text using Gemini (Was Azure)"""
        cache_key = f"{text}_{target_lang}"
        
        # Check cache first
        if cache_key in self.translated_words:
            translation = self.translated_words[cache_key]
            return translation
        
        try:
            # Only call AI if not in cache
            translation = self._call_gemini_translate(text, target_lang)  # Changed function call
            
            if translation:
                self.translated_words[cache_key] = translation  # Update cache
                return translation
            return ""
        except Exception as e:
            print(f"Translation error: {str(e)}")
            return ""

    def _call_gemini_translate(self, text, target_lang):
        """Translate text using Google Gemini API (Replaces Azure)"""
        if not self.model: return ""
        
        # Map mã ngôn ngữ sang tên để Gemini hiểu tốt hơn
        lang_map = {
            'vi': 'Vietnamese', 'en': 'English', 'zh': 'Chinese', 
            'fr': 'French', 'ja': 'Japanese', 'ko': 'Korean',
            'ru': 'Russian', 'es': 'Spanish', 'th': 'Thai'
        }
        target_name = lang_map.get(target_lang, target_lang)

        prompt = f"""
        Translate the following text to {target_name}. 
        Output ONLY the translation. No explanations.
        Text: "{text}"
        """

        for i in range(3): # Retry logic
            try:
                response = self.model.generate_content(prompt)
                return response.text.strip()
            except ResourceExhausted:
                time.sleep(2)
            except Exception as e:
                print(f"Gemini error: {str(e)}")
                return ""
        return ""

    # --- ĐOẠN DƯỚI NÀY GIỮ NGUYÊN 100% NHƯ CODE GỐC CỦA CHỊ ---
    def process_chinese_text(self, text, target_lang="en"):
        """Process Chinese text for word-by-word translation"""
        try:
            # Segment the text using jieba
            words = list(jieba.cut(text))
            
            # Get pinyin for each word
            word_pinyins = []
            for word in words:
                try:
                    char_pinyins = []
                    for char in word:
                        try:
                            char_pinyin = pinyin(char, style=Style.TONE)[0][0]
                            char_pinyins.append(char_pinyin)
                        except Exception as e:
                            print(f"Error getting pinyin for char '{char}': {str(e)}")
                            char_pinyins.append("")
                    word_pinyins.append(' '.join(char_pinyins))
                except Exception as e:
                    print(f"Error processing word '{word}' for pinyin: {str(e)}")
                    word_pinyins.append("")
            
            # Get translations (Logic gọi hàm translate_text đã được trỏ sang Gemini ở trên)
            word_translations = []
            
            # 使用类级别的缓存
            cache_key = f"{word}_{target_lang}"
            for word in words:
                try:
                    # Skip translation for punctuation and numbers
                    if (len(word.strip()) == 1 and not '\u4e00' <= word <= '\u9fff') or word.isdigit():
                        word_translations.append("")
                        continue
                    
                    # 检查缓存
                    cache_key = f"{word}_{target_lang}"
                    if cache_key in self.translated_words:
                        translation = self.translated_words[cache_key]
                        # print(f"Cache hit: '{word}' -> '{translation}'")
                    else:
                        # Add delay between requests
                        time.sleep(0.5)
                        
                        # Translate using Gemini (via wrapper)
                        translation = self.translate_text(word, target_lang)
                        self.translated_words[cache_key] = translation  # 更新缓存
                        # print(f"New translation: '{word}' -> '{translation}'")
                    
                    if translation:
                        word_translations.append(translation)
                    else:
                        word_translations.append("")
                    
                except Exception as e:
                    print(f"Translation error for word '{word}': {str(e)}")
                    word_translations.append("")
            
            # Combine results
            processed_words = []
            for i, (word, pinyin_text, translation) in enumerate(zip(words, word_pinyins, word_translations)):
                try:
                    if '\u4e00' <= word <= '\u9fff':
                        processed_words.append({
                            'word': word,
                            'pinyin': pinyin_text,
                            'translations': [translation] if translation else []
                        })
                    else:
                        processed_words.append({
                            'word': word,
                            'pinyin': '',
                            'translations': []
                        })
                except Exception as e:
                    print(f"Error combining results for word at index {i}: {str(e)}")
                    processed_words.append({
                        'word': word,
                        'pinyin': '',
                        'translations': []
                    })
            
            return processed_words
            
        except Exception as e:
            print(f"Error processing text: {str(e)}")
            return None
