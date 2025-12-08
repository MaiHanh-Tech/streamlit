import google.generativeai as genai
import streamlit as st
import json
import re
import time
from google.api_core.exceptions import ResourceExhausted
from pypinyin import pinyin, Style 

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
                
                # Cấu hình Model (Ưu tiên 2.5 Pro -> Flash)
                try:
                    self.model = genai.GenerativeModel('gemini-2.0-pro-exp') # Hoặc gemini-1.5-pro tuỳ key
                except:
                    try:
                        self.model = genai.GenerativeModel('gemini-1.5-pro')
                    except:
                        self.model = genai.GenerativeModel('gemini-1.5-flash')
                        
            except Exception as e:
                st.error(f"Lỗi cấu hình API Gemini: {str(e)}")
                self.model = None
                
            self.translated_words = {} # Cache
            self.initialized = True

    def _run_gemini_safe(self, prompt, is_json=False):
        """Hàm gọi AI an toàn, chống lỗi Quota"""
        if not self.model: return None
        for i in range(3):
            try:
                response = self.model.generate_content(prompt)
                if is_json:
                    # Dọn dẹp JSON để tránh lỗi cú pháp
                    json_str = response.text.strip()
                    # Xóa markdown code block nếu có
                    if "```" in json_str:
                        json_str = re.sub(r'```json|```', '', json_str).strip()
                    return json.loads(json_str)
                return response.text
            except ResourceExhausted: 
                time.sleep(5) # Nghỉ 5s nếu hết quota rồi thử lại
            except Exception as e:
                return None
        return None

    def translate_text(self, text, source_lang_code, target_lang_code, include_english):
        """Dịch cả đoạn văn với PROMPT CHUYÊN GIA CAO CẤP"""
        
        # Cache key để không phải dịch lại câu đã dịch
        cache_key = f"{text}_expert_{source_lang_code}_{target_lang_code}_{include_english}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]
        
        # Map tên ngôn ngữ từ code
        lang_map = {v: k for k, v in st.session_state.get('languages', {}).items()}
        target_lang_name = lang_map.get(target_lang_code, target_lang_code)
        source_lang_name = lang_map.get(source_lang_code, source_lang_code)
        
        # Logic: Chỉ yêu cầu dịch thêm tiếng Anh nếu Đích và Nguồn đều KHÔNG phải là Anh
        should_ask_english = include_english and target_lang_code != 'en' and source_lang_code != 'en'
        
        # --- PROMPT "CHUYÊN GIA" CỦA CHỊ ---
        base_prompt = f"""
        Bạn là một chuyên gia dịch thuật có nhiều kinh nghiệm trong việc chuyển ngữ các văn bản phức tạp.
        Hãy phân tích và dịch tài liệu dưới đây từ **{source_lang_name}** sang **{target_lang_name}** với độ chính xác cao.
        
        TIÊU CHUẨN DỊCH THUẬT:
        1. **Tinh thần & Văn phong:** Đảm bảo giữ nguyên tinh thần, ý nghĩa, văn phong và sắc thái ngữ nghĩa của tác giả.
        2. **Thuật ngữ chuyên ngành:** Dịch phù hợp với ngữ cảnh và cung cấp ghi chú giải thích nếu cần.
        3. **Điển tích & Thành ngữ:** Tìm cách chuyển tải phù hợp với văn hóa của ngôn ngữ đích ({target_lang_name}) mà vẫn giữ được tinh thần nguyên bản.
        4. **Từ đa nghĩa:** Chọn từ ngữ mượt mà nhất, bỏ bớt từ thừa/lặp để câu văn tự nhiên.
        5. **Cấu trúc:** Giữ nguyên cấu trúc của tài liệu gốc (tiêu đề, số thứ tự, đoạn văn...).
        """

        # Yêu cầu định dạng đầu ra (để code Python cắt được dòng)
        if should_ask_english:
            base_prompt += f"""
            \nĐỊNH DẠNG ĐẦU RA (BẮT BUỘC - 2 DÒNG):
            - Dòng 1: Bản dịch {target_lang_name} (Theo tiêu chuẩn chuyên gia ở trên).
            - Dòng 2: Bản dịch Tiếng Anh.
            - KHÔNG thêm lời dẫn, KHÔNG giải thích dài dòng ngoài bản dịch.
            """
        else:
            base_prompt += f"""
            \nĐỊNH DẠNG ĐẦU RA (BẮT BUỘC):
            - Chỉ cung cấp bản dịch {target_lang_name} (Theo tiêu chuẩn chuyên gia ở trên).
            - KHÔNG trích dẫn lại câu hỏi, KHÔNG giải thích thêm.
            """

        base_prompt += f"""
        \nTOÀN BỘ NỘI DUNG ĐƯỢC CUNG CẤP SAU ĐÂY:
        "{text}"
        """
        
        # Gọi Gemini
        translation = self._run_gemini_safe(base_prompt)
        
        if translation:
            self.translated_words[cache_key] = translation
        return translation or ""

    def process_chinese_text(self, word, target_lang_code):
        """Phân tích từ (Interactive Mode) - Dành cho chế độ học từ"""
        
        # 1. Lấy Pinyin (Nếu là tiếng Trung)
        pinyin_text = ""
        try:
            pinyin_list = pinyin(word, style=Style.TONE)[0][0]
            pinyin_text = ' '.join(pinyin_list)
        except: pass
        
        # 2. Kiểm tra Cache
        cache_key = f"{word}_int_{target_lang_code}"
        if cache_key in self.translated_words:
            return self.translated_words[cache_key]
        
        # 3. Lấy tên ngôn ngữ
        lang_map = {v: k for k, v in st.session_state.get('languages', {}).items()}
        target_lang_name = lang_map.get(target_lang_code, target_lang_code)

        # 4. Prompt phân tích từ
        prompt = f"""
        Analyze this word: "{word}"
        Target Language: {target_lang_name}
        
        Return a JSON ARRAY where each object has a 'translations' key.
        The 'translations' list should contain the meaning in {target_lang_name} and optionally English.
        
        Example Format: [{{ "word": "{word}", "translations": ["Nghĩa 1", "Meaning 1"] }}]
        """
        
        data = self._run_gemini_safe(prompt, is_json=True)
        if data and isinstance(data, list) and len(data) > 0:
            result = {
                'word': word,
                'pinyin': pinyin_text,
                'translations': data[0].get('translations', [])
            }
            self.translated_words[cache_key] = [result]
            return [result]
        
        # Trả về lỗi nhẹ nếu không dịch được
        return [{'word': word, 'pinyin': pinyin_text, 'translations': ['...']}]
