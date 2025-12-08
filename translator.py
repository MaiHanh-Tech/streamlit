import google.generativeai as genai
import streamlit as st
import json
import re

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
                # Trượt về Gemini-Pro (Dự phòng)
                self.model = genai.GenerativeModel('gemini-pro')
                self.model_name = "gemini-pro"

    def translate_standard(self, text, source_lang, target_lang):
        """Dịch cả đoạn văn bình thường"""
        prompt = f"""
        Act as a professional translator.
        Translate the following text from {source_lang} to {target_lang}.
        Maintain the original tone and style.
        
        Text:
        {text}
        """
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"Error: {str(e)}"

    def analyze_paragraph(self, text, source_lang, target_lang):
        """Phân tích từng từ (Interactive Mode)"""
        
        # Nếu là tiếng Trung thì cần Pinyin, nếu không thì cần IPA hoặc để trống
        extra_instruction = ""
        if "Chinese" in source_lang or "Trung" in source_lang:
            extra_instruction = "Include 'pinyin' key for pronunciation."
        elif "English" in source_lang or "Anh" in source_lang:
            extra_instruction = "Include 'pinyin' key, but put IPA pronunciation there."
        else:
            extra_instruction = "Include 'pinyin' key, but leave it empty string."

        prompt = f"""
        Analyze the following text for language learners.
        Source Language: {source_lang}
        Target Language: {target_lang}
        
        Task: Break down the text into meaningful words/phrases.
        
        Return a JSON array of objects. Each object must have:
        - "word": The original word/phrase.
        - "pinyin": {extra_instruction}
        - "translation": Meaning in {target_lang}.
        
        Text: "{text}"
        
        Return ONLY valid JSON. No markdown formatting.
        Example format: [{{"word": "Hello", "pinyin": "/həˈləʊ/", "translation": "Xin chào"}}]
        """
        
        try:
            response = self.model.generate_content(prompt)
            cleaned_text = response.text.strip()
            # Xóa các ký tự markdown nếu AI lỡ thêm vào
            if "```json" in cleaned_text:
                cleaned_text = re.search(r'```json\s*(\[.*?\])\s*```', cleaned_text, re.DOTALL).group(1)
            elif "```" in cleaned_text:
                cleaned_text = cleaned_text.replace("```", "")
                
            return json.loads(cleaned_text)
        except Exception as e:
            st.error(f"AI Error: {e}")
            return []
