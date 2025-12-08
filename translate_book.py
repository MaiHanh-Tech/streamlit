import pypinyin
import re
import os
from concurrent.futures import ThreadPoolExecutor
from typing import List
from tqdm import tqdm
import time
import random
import streamlit as st

def split_sentence(text: str) -> List[str]:
    """
    Tách câu thông minh:
    - Tiếng Anh: Chỉ tách ở . ? ! hoặc xuống dòng (giữ nguyên dấu phẩy).
    - Tiếng Trung: Tách ở 。！？
    """
    text = text.strip()
    if not text: return []

    # 1. Xử lý sơ bộ khoảng trắng
    text = re.sub(r'\s+', ' ', text)

    # 2. Định nghĩa điểm cắt
    # Nếu là tiếng Trung (có ký tự Unicode cao) -> Cắt dày hơn
    # Nếu là tiếng Anh -> Chỉ cắt ở dấu kết thúc câu (.!?)
    is_chinese = any(u'\u4e00' <= c <= u'\u9fff' for c in text[:100])
    
    if is_chinese:
        pattern = r'([。！？…][」"』\'）)]*(?:\s*[「""『\'（(]*)?)'
    else:
        # Tiếng Anh: Cắt ở . ! ? theo sau là khoảng trắng và chữ cái viết hoa hoặc kết thúc dòng
        # Logic này tránh cắt nhầm vào số thập phân (vd: 3.5) hoặc tên viết tắt (Mr. A)
        pattern = r'([.!?]+)(?=\s+|$)'

    splits = re.split(pattern, text)
    
    chunks = []
    current = ""
    
    # 3. Logic ghép lại (Merge) để tránh câu quá ngắn
    # Tiếng Anh cần ngữ cảnh dài hơn tiếng Trung
    min_len = 20 if is_chinese else 150 

    for s in splits:
        if not s.strip(): continue
        
        # Nếu đoạn hiện tại + đoạn mới vẫn ngắn -> Ghép vào
        if len(current) + len(s) < min_len:
            current += s
        else:
            # Nếu đoạn hiện tại đã đủ dài -> Đẩy vào danh sách
            if current: chunks.append(current.strip())
            current = s
            
    # Đẩy đoạn cuối cùng vào
    if current: chunks.append(current.strip())
    
    return chunks

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
    time.sleep(random.uniform(0.1, 0.3))
    try:
        # 1. Pinyin (Chỉ cho tiếng Trung)
        pinyin_text = convert_to_pinyin(chunk, pinyin_style) if source_code == 'zh' else ''

        # 2. Xử lý Dịch
        # TRƯỜNG HỢP: Nguồn là Anh -> Đích là Việt (Không cần dịch ngược sang Anh)
        if (source_code == 'en' or source_code == 'English') and include_english:
            # Chỉ bảo AI dịch sang Target
            target_val = translate_text(chunk, source_code, target_code, False).strip()
            english_val = chunk # Lấy gốc làm Anh
            return (index, chunk, pinyin_text, english_val, target_val)
            
        else:
            # Các trường hợp khác
            full_trans = translate_text(chunk, source_code, target_code, include_english)
            parts = [p.strip() for p in full_trans.split('\n') if p.strip()]
            
            if include_english and target_code != 'en':
                # Hy vọng: Dòng 1 = Đích, Dòng 2 = Anh
                target_val = parts[0] if len(parts) > 0 else "..."
                english_val = parts[1] if len(parts) > 1 else "..."
                return (index, chunk, pinyin_text, english_val, target_val)
            else:
                target_val = parts[0] if len(parts) > 0 else "..."
                return (index, chunk, pinyin_text, target_val)

    except Exception as e:
        err_msg = f"[Error: {str(e)}]"
        return (index, chunk, "", chunk, err_msg) if include_english else (index, chunk, "", err_msg)

def create_html_block(results, include_english):
    speak_btn = '''<button class="speak-button" onclick="speakSentence(this.parentElement.textContent.replace('🔊', ''))"><svg viewBox="0 0 24 24"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg></button>'''
    
    if include_english:
        idx, orig, pin, eng, sec = results
        pinyin_div = f'<div class="pinyin">{pin}</div>' if pin else ''
        return f'''<div class="sentence-part responsive"><div class="original">{idx+1}. {orig}{speak_btn}</div>{pinyin_div}<div class="english">{eng}</div><div class="second-language">{sec}</div></div>'''
    else:
        idx, orig, pin, sec = results
        pinyin_div = f'<div class="pinyin">{pin}</div>' if pin else ''
        return f'''<div class="sentence-part responsive"><div class="original">{idx+1}. {orig}{speak_btn}</div>{pinyin_div}<div class="second-language">{sec}</div></div>'''

def create_interactive_html_block(results, include_english):
    # Interactive mode placeholder
    return "Interactive mode is optimized for Chinese-learning only."

def translate_file(input_text, progress_callback=None, include_english=True, source_lang='zh', target_lang='vi', pinyin_style='tone_marks', translation_mode="Standard Translation", processed_words=None):
    chunks = split_sentence(input_text)
    total = len(chunks)
    html = ""
    
    # Giảm số luồng xuống 3 để tránh quá tải API khi dịch đoạn dài
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = []
        for i, chunk in enumerate(chunks):
            futures.append(ex.submit(process_chunk, chunk, i, ex, include_english, source_lang, target_lang, pinyin_style))
        
        results = []
        done = 0
        for f in futures:
            try:
                results.append(f.result())
            except: 
                pass # Bỏ qua lỗi luồng
            done += 1
            if progress_callback: progress_callback(done/total * 100)
            
    results.sort(key=lambda x: x[0])
    
    for res in results:
        html += create_html_block(res, include_english)
        
    with open('template.html', 'r', encoding='utf-8') as f:
        template = f.read()
    return template.replace('{{content}}', html)
