import pypinyin
import re
import os
from concurrent.futures import ThreadPoolExecutor
from typing import List
import time
import random
import streamlit as st

# --- HÀM MỚI: HÀN GẮN VĂN BẢN VỠ ---
def preprocess_text(text: str) -> str:
    """
    Hàn gắn các dòng bị ngắt quãng do PDF/OCR.
    Ví dụ: "Hello\nWorld" -> "Hello World"
    Nhưng vẫn giữ lại đoạn văn thật sự (cách nhau 2 dòng enter).
    """
    # 1. Thay thế các dòng xuống dòng đơn lẻ bằng khoảng trắng
    # (Giữ lại xuống dòng kép \n\n là dấu hiệu sang đoạn mới)
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    
    # 2. Xóa khoảng trắng thừa
    text = re.sub(r'\s+', ' ', text)
    
    # 3. Sửa lỗi dính chữ thường gặp trong PDF (vd: "eld,suchas" -> "eld, suchas")
    text = re.sub(r'([a-z]),([a-z])', r'\1, \2', text)
    
    return text.strip()

def split_text_into_blocks(text: str, block_size=2000) -> List[str]:
    """
    Thay vì cắt câu nhỏ (dễ lỗi ngữ cảnh), ta cắt thành các KHỐI LỚN (Block).
    Mỗi khối khoảng 2000 ký tự để AI hiểu ngữ cảnh và dịch mượt.
    """
    # Bước 1: Làm sạch văn bản trước
    clean_text = preprocess_text(text)
    
    # Bước 2: Tách theo dấu kết thúc câu để không cắt dở dang
    # Tách tại dấu chấm/hỏi/thang theo sau là khoảng trắng
    sentences = re.split(r'([.!?]+)\s+', clean_text)
    
    blocks = []
    current_block = ""
    
    # Ghép lại thành từng khối lớn
    for part in sentences:
        if len(current_block) + len(part) < block_size:
            current_block += part + " " # Thêm khoảng trắng nối
        else:
            if current_block: blocks.append(current_block.strip())
            current_block = part + " "
            
    if current_block: blocks.append(current_block.strip())
    
    return blocks

def convert_to_pinyin(text, style='tone_marks'):
    try:
        p_style = pypinyin.TONE3 if style == 'tone_numbers' else pypinyin.TONE
        return ' '.join([i[0] for i in pypinyin.pinyin(text, style=p_style)])
    except: return ""

def translate_text(text, source, target, include_eng):
    if 'translator' not in st.session_state:
        from translator import Translator
        st.session_state.translator = Translator()
    return st.session_state.translator.translate_text(text, source, target, include_eng)

def process_chunk(chunk, index, executor, include_english, source_code, target_code, pinyin_style):
    # Nghỉ xíu để server thở
    time.sleep(random.uniform(0.5, 1.0)) 
    
    try:
        # Pinyin (Chỉ cho tiếng Trung)
        pinyin_text = convert_to_pinyin(chunk, pinyin_style) if source_code == 'zh' else ''

        # XỬ LÝ DỊCH
        # Nếu nguồn là Anh (en) -> Đích (vi), và có chọn Include English
        if (source_code == 'en' or source_code == 'English') and include_english:
            # Chỉ bảo AI dịch sang Target (Việt)
            # Quan trọng: Chunk ở đây là khối lớn (2000 từ), AI sẽ dịch cả khối
            target_val = translate_text(chunk, source_code, target_code, False)
            english_val = chunk 
            
            return (index, chunk, pinyin_text, english_val, target_val)
            
        else:
            # Các ngôn ngữ khác
            full_trans = translate_text(chunk, source_code, target_code, include_english)
            
            # Cố gắng tách dòng nếu AI trả về 2 dòng
            parts = full_trans.split('\n', 1) # Chỉ tách 1 lần
            
            if include_english and target_code != 'en' and len(parts) >= 2:
                target_val = parts[0].strip()
                english_val = parts[1].strip()
                return (index, chunk, pinyin_text, english_val, target_val)
            else:
                target_val = full_trans.strip()
                return (index, chunk, pinyin_text, target_val)

    except Exception as e:
        return (index, chunk, "", chunk, f"[Error: {str(e)}]")

def create_html_block(results, include_english):
    speak_btn = '''<button class="speak-button" onclick="speakSentence(this.parentElement.textContent.replace('🔊', ''))"><svg viewBox="0 0 24 24"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg></button>'''
    
    if include_english:
        idx, orig, pin, eng, sec = results
        # Pinyin div
        pin_html = f'<div class="pinyin">{pin}</div>' if pin else ''
        return f'''
        <div class="sentence-part responsive">
            <div class="original">{idx+1}. {orig} {speak_btn}</div>
            {pin_html}
            <div class="second-language">{sec}</div>
            <div class="english" style="color: #666; font-size: 0.9em; margin-top: 5px;">(Gốc/Anh: {eng})</div>
        </div>
        '''
    else:
        idx, orig, pin, sec = results
        pin_html = f'<div class="pinyin">{pin}</div>' if pin else ''
        return f'''
        <div class="sentence-part responsive">
            <div class="original">{idx+1}. {orig} {speak_btn}</div>
            {pin_html}
            <div class="second-language">{sec}</div>
        </div>
