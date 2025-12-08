import google.generativeai as genai
import streamlit as st
import json
import time
import jieba
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
                # 1. Cấu hình Gemini
                api_key = st.secrets["api_keys"]["gemini_api_key"]
                genai.configure(api_key=api_key)
                
                # 2. Chọn Model (2.5 Pro -> 2.5 Flash -> 1.5 Pro)
                try:
                    self.model = genai.GenerativeModel('gemini-2.5-pro')
                except:
                    try:
                        self.model = genai.GenerativeModel('gemini-2.5-flash')
                    except:
                        try:
                            self.model = genai.GenerativeModel('gemini-1.5-pro')
                        except:
                            self.model = genai.GenerativeModel('gemini-1.5-flash')
            
            except Exception as e:
                # st.error(f"Gemini Error: {str(e)}") # Ẩn lỗi init để không làm rối giao diện
                self.model = None
                
            self.translated_words = {} # Cache
            self.initialized = True

    def _run_gemini(self, prompt):
        """Hàm gọi AI an toàn"""
        if not self.model: return None
        
        for i in range(3): # Thử lại 3 lần
            try:
                # Tắt bộ lọc an toàn
                safety = [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                ]
                response = self.model.generate_content(prompt, safety_settings=safety)
                return response.text.strip()
            except ResourceExhausted:
                time.sleep(2) # Nghỉ nếu hết quota
            except Exception:
                time.sleep(1)
        return None

    def translate_text(self, text, target_lang):
        """
        Thay thế hàm _call_azure_translate cũ.
        Dùng Gemini để dịch text.
        """
        if not text.strip(): return ""

        cache_key = f"{text}_{target_lang}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]

        # Map mã ngôn ngữ sang tên tiếng Anh (Gemini hiểu tên tốt hơn mã)
        lang_map = {
            'vi': 'Vietnamese', 'en': 'English', 'fr': 'French',
            'ja': 'Japanese', 'ko': 'Korean', 'ru': 'Russian', 
            'es': 'Spanish', 'th': 'Thai', 'zh': 'Chinese', 
            'ar': 'Arabic', 'id': 'Indonesian', 'it': 'Italian',
            'fa': 'Persian', 'pt': 'Portuguese', 'uz': 'Uzbek'
        }
        target_name = lang_map.get(target_lang, target_lang)

        prompt = f"""
        Translate the following text to {target_name}. 
        Output ONLY the translation. No explanations.
        Text: "{text}"
        """
        
        translation = self._run_gemini(prompt)
        
        if translation:
            self.translated_words[cache_key] = translation
            return translation
        return ""

    def process_chinese_text(self, text, target_lang="en"):
        """
        Giữ nguyên logic Jieba + Pypinyin của code gốc,
        chỉ thay đoạn gọi Azure bằng Gemini.
        """
        try:
            # 1. Cắt từ (Jieba)
            words = list(jieba.cut(text))
            
            # 2. Lấy Pinyin (Pypinyin - Local, nhanh)
            word_pinyins = []
            for word in words:
                try:
                    char_pinyins = []
                    for char in word:
                        try:
                            # Lấy pinyin có dấu thanh
                            char_pinyin = pinyin(char, style=Style.TONE)[0][0]
                            char_pinyins.append(char_pinyin)
                        except:
                            char_pinyins.append("")
                    word_pinyins.append(' '.join(char_pinyins))
                except:
                    word_pinyins.append("")
            
            # 3. Dịch từng từ (Dùng Gemini thay Azure)
            word_translations = []
            
            for word in words:
                try:
                    # Bỏ qua dấu câu hoặc số
                    if (len(word.strip()) == 1 and not '\u4e00' <= word <= '\u9fff') or word.isdigit():
                        word_translations.append("")
                        continue
                    
                    # Gọi hàm dịch Gemini ở trên
                    # Lưu ý: Dịch từng từ rất tốn API, nhưng giữ nguyên logic cũ theo yêu cầu
                    translation = self.translate_text(word, target_lang)
                    
                    if translation:
                        word_translations.append(translation)
                    else:
                        word_translations.append("")
                        
                except Exception as e:
                    print(f"Translation error for word '{word}': {str(e)}")
                    word_translations.append("")
            
            # 4. Gom kết quả (Format y hệt cũ)
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
                except:
                    processed_words.append({
                        'word': word,
                        'pinyin': '',
                        'translations': []
                    })
            
            return processed_words
            
        except Exception as e:
            print(f"Error processing text: {str(e)}")
            return None
