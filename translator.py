import google.generativeai as genai
import streamlit as st
import json
import re
import time
from pydantic import BaseModel, Field
from google.api_core.exceptions import ResourceExhausted
from pypinyin import pinyin, Style 
from typing import List, Optional # <--- DÒNG NÀY ĐÃ ĐƯỢC THÊM

# --- 1. KHUÔN DỮ LIỆU (PYDANTIC SCHEMAS) ---
class StandardTranslation(BaseModel):
    # Dùng cho chế độ dịch câu/đoạn
    target_text: str = Field(description="Bản dịch chính thức sang ngôn ngữ đích.")
    english_text: str = Field(description="Bản dịch Tiếng Anh (hoặc văn bản gốc nếu nguồn là Anh).")

class InteractiveWord(BaseModel):
    # Dùng cho chế độ phân tích từ
    word: str = Field(description="Từ/Cụm từ gốc (tiếng Trung).")
    pinyin: str = Field(description="Phiên âm Pinyin có dấu thanh.")
    translations: List[str] = Field(description="Danh sách các nghĩa của từ.")

# --- 2. AGENT ENGINE (TÁI CẤU TRÚC LẠI CLASS) ---
class Translator:
    def __init__(self):
        try:
            # Import pydantic-ai tại đây (để tránh lỗi import sớm)
            from pydantic_ai import Agent 
            self.Agent = Agent
            
            api_key = st.secrets["api_keys"]["gemini_api_key"]
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
            self.agent_map = {}
        except Exception as e:
            self.model = None
            # Dòng này giúp debug nếu thiếu thư viện:
            # st.error(f"Lỗi Init Translator: {e}")
            
        self.translated_words = {}
        self.initialized = True

    def _get_agent(self, schema: BaseModel, system_instruction: str):
        """Lấy hoặc tạo Agent mới với schema/cấu hình cụ thể"""
        key = (schema.__name__, system_instruction)
        if key not in self.agent_map:
            config = genai.types.GenerateContentConfig(
                temperature=0.1,
                system_instruction=system_instruction
            )
            
            self.agent_map[key] = self.Agent(
                'google-gla:gemini-1.5-flash',
                result_type=schema,
                system_prompt=system_instruction,
                config=config 
            )
        return self.agent_map[key]

    def translate_standard(self, text, source_lang, target_lang, include_english):
        """Dịch chuẩn (Sử dụng Pydantic Agent)"""
        # Cấu hình cho Standard Mode
        if source_lang == 'zh':
            system_prompt = f"Bạn là dịch giả chuyên nghiệp. Dịch văn bản từ Tiếng Trung sang {target_lang}. Giữ nguyên định dạng và số thứ tự."
        else:
             system_prompt = f"Bạn là dịch giả chuyên nghiệp. Dịch văn bản từ {source_lang} sang {target_lang}. Giữ nguyên định dạng và số thứ tự."

        agent = self._get_agent(StandardTranslation, system_prompt)
        
        # Tạo prompt tùy biến cho Gemini
        if include_english and target_lang != 'en' and source_lang != 'en':
            prompt = f"Translate the text below. Target: {target_lang}. Also provide the corrected English text: \n{text}"
        else:
            prompt = f"Translate the text below. Target: {target_lang}. \n{text}"

        try:
            # Gọi Agent.run_sync() để lấy kết quả (tự xử lý JSON/lỗi)
            result = agent.run_sync(prompt)
            return result.data # Trả về đối tượng Pydantic

        except Exception as e:
            # Fallback thô
            print(f"Pydantic Error, falling back to raw: {e}")
            raw_prompt = f"Translate the text below to {target_lang}. Just the translation. Text: {text}"
            raw_res = self._run_gemini_safe(raw_prompt)
            # Trả về đối tượng Pydantic đã được điền thông tin Fallback
            return StandardTranslation(target_text=raw_res or "[Lỗi dịch thuật]", english_text="...").data

    def process_chinese_text(self, word, target_lang):
        """Phân tích từ (Sử dụng Pydantic Agent cho từ vựng)"""
        system_prompt = "Bạn là trợ lý học tiếng Trung. Phân tích từ vựng và phiên âm."
        agent = self._get_agent(InteractiveWord, system_prompt)
        
        try:
            result = agent.run_sync(f"Analyze the Chinese word '{word}' and translate it to {target_lang}.")
            return [result.data] # Trả về list of objects để khớp với code cũ
        except Exception as e:
            return [{'word': word, 'pinyin': '', 'translations': [f"Error: {e}"]}]

    def _run_gemini_safe(self, prompt):
        # Hàm gọi thô cho fallback (giữ nguyên)
        if not self.model: return None
        for i in range(3):
            try:
                response = self.model.generate_content(prompt)
                return response.text.strip()
            except Exception: time.sleep(1)
        return None
