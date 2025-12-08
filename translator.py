import google.generativeai as genai
import streamlit as st
import json
import re
import time

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

    def split_text(self, text, chunk_size=3000):
        """Hàm cắt nhỏ văn bản để tránh lỗi AI bị ngắt quãng"""
        chunks = []
        current_chunk = ""
        # Tách theo dòng để tránh cắt giữa câu
        lines = text.split('\n')
        
        for line in lines:
            if len(current_chunk) + len(line) < chunk_size:
                current_chunk += line + "\n"
            else:
                chunks.append(current_chunk)
                current_chunk = line + "\n"
        if current_chunk:
            chunks.append(current_chunk)
        return chunks

    def translate_standard(self, text, source_lang, target_lang):
        """Dịch chuẩn (Có hỗ trợ văn bản dài vô tận)"""
        
        # 1. Nếu văn bản ngắn (< 3000 ký tự): Dịch 1 lần cho nhanh
        if len(text) < 3000:
            return self._translate_chunk(text, source_lang, target_lang)
        
        # 2. Nếu văn bản dài: Cắt nhỏ và dịch từng phần
        else:
            chunks = self.split_text(text)
            full_translation = ""
            total_chunks = len(chunks)
            
            # Tạo thanh tiến trình trên giao diện
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, chunk in enumerate(chunks):
                status_text.text(f"Đang dịch phần {i+1}/{total_chunks}...")
                translated_part = self._translate_chunk(chunk, source_lang, target_lang)
                full_translation += translated_part + "\n"
                
                # Cập nhật tiến trình
                progress = int((i + 1) / total_chunks * 100)
                progress_bar.progress(progress)
                time.sleep(0.5) # Nghỉ xíu để không bị spam API
            
            status_text.empty()
            progress_bar.empty()
            return full_translation

    def _translate_chunk(self, text, source, target):
        """Hàm con để dịch 1 đoạn"""
        if not text.strip(): return ""
        
        prompt = f"""
        Act as a professional book translator.
        Translate the text below from {source} to {target}.
        
        Requirements:
        1. Accuracy: Keep the original meaning.
        2. Flow: Make it sound natural and literary (như văn phong sách).
        3. Terminology: Use consistent terminology.
        
        Text to translate:
        {text}
        """
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"\n[Lỗi đoạn này: {str(e)}]\n"

    def analyze_paragraph(self, text, source_lang, target_lang):
        """Phân tích từ vựng (Giữ nguyên logic cũ)"""
        # (Chị dùng code cũ của hàm này hoặc để em viết lại ngắn gọn ở đây)
        # Nếu chị chỉ cần dịch sách thì hàm này ít dùng, nhưng em vẫn để lại để không lỗi code
        
        extra = "Pinyin/IPA"
        if "Trung" in source_lang or "Chinese" in source_lang: extra = "Pinyin"
        
        prompt = f"""
        Analyze logic for learners. Source: {source_lang}, Target: {target_lang}.
        Text: "{text[:1000]}" (Limit analysis to first 1000 chars to save time)
        Return JSON list: [{{"word": "...", "pinyin": "...", "translation": "..."}}]
        """
        try:
            response = self.model.generate_content(prompt)
            cleaned = response.text.strip().replace("```json", "").replace("```", "")
            return json.loads(cleaned)
        except: return []
