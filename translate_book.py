import pypinyin
import re
import os
from concurrent.futures import ThreadPoolExecutor
from typing import List
import time
import random
import streamlit as st

# --- CÁC HÀM XỬ LÝ VĂN BẢN (PRE-PROCESSING) ---

def preprocess_text(text: str) -> str:
    """Hàn gắn các dòng bị ngắt quãng do PDF/OCR."""
    if not text: return ""
    # 1. Thay thế xuống dòng đơn lẻ bằng khoảng trắng
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    # 2. Xóa khoảng trắng thừa
    text = re.sub(r'\s+', ' ', text)
    # 3. Sửa lỗi dính chữ (vd: "eld,suchas" -> "eld, suchas")
    text = re.sub(r'([a-z]),([a-z])', r'\1, \2', text)
    return text.strip()

def split_text_into_blocks(text: str, block_size=2000) -> List[str]:
    """Cắt văn bản thành các khối lớn để giữ ngữ cảnh."""
    clean_text = preprocess_text(text)
    if not clean_text: return []
    
    # Tách tại dấu kết thúc câu (.!?)
    sentences = re.split(r'([.!?]+)\s+', clean_text)
    
    blocks = []
    current_block = ""
    
    for part in sentences:
        if len(current_block) + len(part) < block_size:
            current_block += part + " "
        else:
            if current_block: blocks.append(current_block.strip())
            current_block = part + " "
            
    if current_block: blocks.append(current_block.strip())
    return blocks

def convert_to_pinyin(text, style='tone_marks'):
    """Chuyển đổi Pinyin cho tiếng Trung."""
    try:
        p_style = pypinyin.TONE3 if style == 'tone_numbers' else pypinyin.TONE
        return ' '.join([i[0] for i in pypinyin.pinyin(text, style=p_style)])
    except: 
        return ""

def translate_text(text, source, target, include_eng):
    """Gọi hàm dịch từ Translator (Lazy import để tránh lỗi vòng lặp)."""
    if 'translator' not in st.session_state:
        from translator import Translator
        st.session_state.translator = Translator()
    return st.session_state.translator.translate_text(text, source, target, include_eng)

def process_chunk(chunk, index, executor, include_english, source_code, target_code, pinyin_style):
    """Xử lý dịch từng khối văn bản."""
    time.sleep(random.uniform(0.5, 1.0)) 
    
    try:
        # 1. Pinyin (Chỉ nếu nguồn là Trung)
        pinyin_text = convert_to_pinyin(chunk, pinyin_style) if source_code == 'zh' else ''

        # 2. Xử lý Dịch
        # Nếu nguồn là Anh (en) -> Đích (vi), và có chọn Include English
        # Ta lấy luôn văn bản gốc làm cột Tiếng Anh
        is_source_english = (source_code == 'en' or source_code == 'English')
        
        if is_source_english and include_english:
            target_val = translate_text(chunk, source_code, target_code, False).strip()
            english_val = chunk 
            return (index, chunk, pinyin_text, english_val, target_val)
            
        else:
            # Các ngôn ngữ khác: AI trả về 2 dòng
            full_trans = translate_text(chunk, source_code, target_code, include_english)
            
            parts = full_trans.split('\n', 1) # Chỉ tách 1 lần ở dòng đầu tiên
            
            if include_english and target_code != 'en':
                # Mong đợi: Dòng 1 = Đích, Dòng 2 = Anh (nếu AI làm đúng)
                # Hoặc AI có thể trả về 1 cục, ta cứ lấy phần đầu làm đích
                if len(parts) >= 2:
                    target_val = parts[0].strip()
                    english_val = parts[1].strip()
                else:
                    target_val = full_trans.strip()
                    english_val = "..." # Không dịch được tiếng Anh thì để ba chấm
                
                return (index, chunk, pinyin_text, english_val, target_val)
            else:
                target_val = full_trans.strip()
                return (index, chunk, pinyin_text, target_val)

    except Exception as e:
        # Trả về lỗi đúng định dạng tuple để không sập App
        err_msg = f"[Error: {str(e)}]"
        if include_english:
            return (index, chunk, "", chunk, err_msg)
        else:
            return (index, chunk, "", err_msg)

def create_html_block(results, include_english):
    """Tạo HTML hiển thị kết quả."""
    # Nút loa phát âm
    speak_btn = '''<button class="speak-button" onclick="speakSentence(this.parentElement.textContent.replace('🔊', ''))"><svg viewBox="0 0 24 24"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg></button>'''
    
    if include_english:
        # Unpack 5 biến
        idx, orig, pin, eng, sec = results
        
        # Ẩn Pinyin nếu không có
        pin_html = f'<div class="pinyin">{pin}</div>' if pin else ''
        
        return f'''
        <div class="sentence-part responsive">
            <div class="original">{idx+1}. {orig} {speak_btn}</div>
            {pin_html}
            <div class="second-language">{sec}</div>
            <div class="english" style="color: #666; font-size: 0.9em; margin-top: 8px; font-style: italic; border-top: 1px dashed #eee; padding-top: 4px;">🇬🇧 {eng}</div>
        </div>
        '''
    else:
        # Unpack 4 biến
        idx, orig, pin, sec = results
        pin_html = f'<div class="pinyin">{pin}</div>' if pin else ''
        
        return f'''
        <div class="sentence-part responsive">
            <div class="original">{idx+1}. {orig} {speak_btn}</div>
            {pin_html}
            <div class="second-language">{sec}</div>
        </div>
        '''

def create_interactive_html_block(results, include_english):
    # Placeholder cho chế độ Interactive (không dùng cho dịch sách dài)
    return "<div style='padding:20px; color:red;'>Chế độ tương tác không hỗ trợ văn bản dài. Vui lòng chọn Standard Translation.</div>"

def translate_file(input_text, progress_callback=None, include_english=True, source_lang='zh', target_lang='vi', pinyin_style='tone_marks', translation_mode="Standard Translation", processed_words=None):
    """Hàm chính chạy tiến trình dịch."""
    
    # 1. Cắt văn bản thành khối lớn (Block) để hàn gắn câu
    chunks = split_text_into_blocks(input_text, block_size=2000)
    total = len(chunks)
    html = ""
    
    # 2. Chạy đa luồng (Giới hạn 2 luồng để Gemini không bị quá tải)
    with ThreadPoolExecutor(max_workers=2) as ex:
        futures = []
        for i, chunk in enumerate(chunks):
            futures.append(ex.submit(process_chunk, chunk, i, ex, include_english, source_lang, target_lang, pinyin_style))
        
        results = []
        done = 0
        for f in futures:
            try:
                res = f.result()
                results.append(res)
            except Exception as e:
                print(f"Thread Error: {e}")
            
            done += 1
            if progress_callback: 
                # Tính phần trăm tiến trình
                progress_callback(min(100, int(done/total * 100)))
            
    # 3. Sắp xếp lại theo thứ tự ban đầu
    results.sort(key=lambda x: x[0])
    
    # 4. Tạo HTML
    for res in results:
        html += create_html_block(res, include_english)
        
    # 5. Ghép vào template
    try:
        with open('template.html', 'r', encoding='utf-8') as f:
            template = f.read()
        return template.replace('{{content}}', html)
    except:
        return f"<div>Lỗi: Không tìm thấy file template.html</div>{html}"
