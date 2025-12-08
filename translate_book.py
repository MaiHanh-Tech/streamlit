import pypinyin
import re
import os
from concurrent.futures import ThreadPoolExecutor
from typing import List
import time
import random
import streamlit as st

def preprocess_text(text: str) -> str:
    """Hàn gắn văn bản OCR lỗi"""
    if not text: return ""
    
    # 1. Xóa xuống dòng vớ vẩn
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    
    # 2. Tách chữ dính (suchas -> such as)
    # Tìm: chữ thường + chữ thường (nhưng dính nhau bất thường, khó bắt bằng regex đơn giản)
    # Tạm thời tách dấu câu dính chữ: "needed.y" -> "needed. y"
    text = re.sub(r'([a-z])\.([a-zA-Z])', r'\1. \2', text)
    
    # 3. Xử lý khoảng trắng
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

def split_text_into_blocks(text: str, block_size=2000) -> List[str]:
    clean_text = preprocess_text(text)
    if not clean_text: return []
    
    # Tách theo dấu kết thúc câu
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
    time.sleep(random.uniform(0.5, 1.0))
    try:
        pinyin_text = convert_to_pinyin(chunk, pinyin_style) if source_code == 'zh' else ''

        # LOGIC QUAN TRỌNG: Nguồn Anh -> Đích Việt
        is_english_source = (source_code == 'en' or source_code == 'English')
        
        if is_english_source and include_english:
            # Chỉ dịch sang Việt (False cho include_english của hàm con)
            target_val = translate_text(chunk, source_code, target_code, False).strip()
            english_val = chunk 
            return (index, chunk, pinyin_text, english_val, target_val)
        else:
            full_trans = translate_text(chunk, source_code, target_code, include_english)
            parts = full_trans.split('\n')
            
            if include_english and target_code != 'en' and len(parts) >= 2:
                return (index, chunk, pinyin_text, parts[1].strip(), parts[0].strip())
            else:
                return (index, chunk, pinyin_text, full_trans.strip())

    except Exception as e:
        err = f"[Error: {str(e)}]"
        return (index, chunk, "", chunk, err) if include_english else (index, chunk, "", err)

def create_html_block(results, include_english):
    speak_btn = '''<button class="speak-button" onclick="speakSentence(this.parentElement.textContent.replace('🔊', ''))"><svg viewBox="0 0 24 24"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg></button>'''
    
    if include_english:
        idx, orig, pin, eng, sec = results
        pin_html = f'<div class="pinyin">{pin}</div>' if pin else ''
        return f'''<div class="sentence-part responsive"><div class="original">{idx+1}. {orig} {speak_btn}</div>{pin_html}<div class="second-language" style="color: #d35400; font-weight: bold;">{sec}</div><div class="english" style="color: #7f8c8d; font-size: 0.9em; margin-top:5px; border-top:1px dashed #eee;">(Gốc: {eng})</div></div>'''
    else:
        idx, orig, pin, sec = results
        pin_html = f'<div class="pinyin">{pin}</div>' if pin else ''
        return f'''<div class="sentence-part responsive"><div class="original">{idx+1}. {orig} {speak_btn}</div>{pin_html}<div class="second-language">{sec}</div></div>'''

def create_interactive_html_block(results, include_english):
    return ""

def translate_file(input_text, progress_callback=None, include_english=True, source_lang='zh', target_lang='vi', pinyin_style='tone_marks', translation_mode="Standard Translation", processed_words=None):
    chunks = split_text_into_blocks(input_text, block_size=1500) # Giảm block size chút cho an toàn
    total = len(chunks)
    html = ""
    
    with ThreadPoolExecutor(max_workers=2) as ex:
        futures = []
        for i, chunk in enumerate(chunks):
            futures.append(ex.submit(process_chunk, chunk, i, ex, include_english, source_lang, target_lang, pinyin_style))
        
        results = []
        done = 0
        for f in futures:
            results.append(f.result())
            done += 1
            if progress_callback: progress_callback(done/total * 100)
            
    results.sort(key=lambda x: x[0])
    for res in results: html += create_html_block(res, include_english)
        
    with open('template.html', 'r', encoding='utf-8') as f: template = f.read()
    return template.replace('{{content}}', html)
