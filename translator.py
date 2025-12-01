import google.generativeai as genai
import streamlit as st
import json

class Translator:
    def __init__(self):
        # --- BẢO MẬT TUYỆT ĐỐI ---
        # Không dán Key ở đây. Code sẽ tự mò vào Két sắt (st.secrets) để lấy.
        try:
            # Lấy key từ mục [api_keys] trong secrets
            self.api_key = st.secrets["api_keys"]["gemini_api_key"]
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-2.5-flash')
            self.is_ready = True
        except Exception as e:
            # Nếu không thấy Key, báo lỗi nhưng không crash app
            print(f"Lỗi cấu hình API Key: {e}")
            self.is_ready = False

    def process_chinese_text(self, word, target_lang_code="vi"):
        """Xử lý từng từ (Dùng cho Word-by-Word cũ)"""
        if not self.is_ready:
            return [{'word': word, 'pinyin': 'Lỗi Key', 'translation': 'Chưa nhập API Key'}]

        if not word or word.strip() == "":
            return [{'word': word, 'pinyin': '', 'translation': ''}]

        try:
            # Prompt tối ưu cho Gemini
            prompt = f"""
            Analyze this Chinese word: "{word}"
            Output JSON only: {{"word": "{word}", "pinyin": "pinyin_here", "translation": "meaning_in_{target_lang_code}"}}
            """
            response = self.model.generate_content(prompt)
            clean_json = response.text.replace("```json", "").replace("```", "").strip()
            return [json.loads(clean_json)]
        except:
            return [{'word': word, 'pinyin': '', 'translation': '...'}]

    def analyze_paragraph(self, text, target_lang="Vietnamese"):
        """
        Hàm mới: Xử lý cả đoạn văn (Dùng cho logic mới trong app.py)
        Trả về JSON list các từ đã cắt và dịch.
        """
        if not self.is_ready: return []
        
        try:
            prompt = f"""
            Phân tích đoạn văn tiếng Trung: "{text}"
            Dịch sang: {target_lang}
            
            Yêu cầu:
            1. Cắt từ (Segmentation).
            2. Thêm Pinyin.
            3. Dịch nghĩa từng từ.
            4. Trả về JSON List: [{{ "word": "...", "pinyin": "...", "translation": "..." }}]
            """
            response = self.model.generate_content(prompt)
            clean_json = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_json)
        except Exception as e:
            print(f"Gemini Error: {e}")
            return []
