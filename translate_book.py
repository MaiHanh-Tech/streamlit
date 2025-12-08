import pypinyin
import re
import os
from concurrent.futures import ThreadPoolExecutor
import time
import random
import streamlit as st

def split_sentence(text: str) -> list:
    text = re.sub(r'\s+', ' ', text.strip())
    # Tách câu dựa trên cả dấu chấm câu tiếng Anh và tiếng Trung
    pattern = r'([。！？，：；.!?,][」"』\'）)]*(?:\s*[「""『\'（(]*)?)'
    splits = re.split(pattern, text)
    chunks = []
    current = ""
    for s in splits:
        if not s: continue
        if len(current) + len(s) < 100: # Gom câu ngắn lại
            current += s
        else:
            chunks.append(current)
            current = s
    if current: chunks.append(current)
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
        # 1. Pinyin (Chỉ hiện nếu nguồn là Trung)
        pinyin_text = convert_to_pinyin(chunk, pinyin_style) if source_code == 'zh' else ''

        # 2. Xử lý Dịch
        # LOGIC MỚI: Nếu Nguồn là Anh, ta TỰ LẤY nguồn làm bản dịch Anh
        if source_code == 'en' and include_english:
            # Chỉ bảo AI dịch sang Target (Vd: Việt)
            target_val = translate_text(chunk, source_code, target_code, False).strip()
            english_val = chunk # Lấy gốc làm Anh
            
            return (index, chunk, pinyin_text, english_val, target_val)
            
        else:
            # Logic cũ cho các ngôn ngữ khác (AI trả về 2 dòng nếu cần)
            full_trans = translate_text(chunk, source_code, target_code, include_english)
            parts = full_trans.split('\n')
            parts = [p for p in parts if p.strip()] # Lọc dòng trống
            
            if include_english and target_code != 'en':
                # Hy vọng AI trả về: Dòng 1 Target, Dòng 2 English
                target_val = parts[0] if len(parts) > 0 else "Error"
                english_val = parts[1] if len(parts) > 1 else "Error"
                return (index, chunk, pinyin_text, english_val, target_val)
            else:
                target_val = parts[0] if len(parts) > 0 else "Error"
                return (index, chunk, pinyin_text, target_val)

    except Exception as e:
        return (index, chunk, "", "Error", str(e))

def create_html_block(results, include_english):
    # Nút phát âm
    speak_btn = '''<button class="speak-button" onclick="speakSentence(this.parentElement.textContent.replace('🔊', ''))"><svg viewBox="0 0 24 24"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg></button>'''
    
    if include_english:
        idx, orig, pin, eng, sec = results
        # Ẩn dòng Pinyin nếu trống (khi nguồn không phải Trung)
        pinyin_div = f'<div class="pinyin">{pin}</div>' if pin else ''
        return f'''<div class="sentence-part responsive"><div class="original">{idx+1}. {orig}{speak_btn}</div>{pinyin_div}<div class="english">{eng}</div><div class="second-language">{sec}</div></div>'''
    else:
        idx, orig, pin, sec = results
        pinyin_div = f'<div class="pinyin">{pin}</div>' if pin else ''
        return f'''<div class="sentence-part responsive"><div class="original">{idx+1}. {orig}{speak_btn}</div>{pinyin_div}<div class="second-language">{sec}</div></div>'''

def create_interactive_html_block(results, include_english):
    # (Giữ nguyên logic cũ của hàm này hoặc copy từ bản trước nếu cần dùng Interactive)
    # Vì chị đang hỏi về dịch sách (Standard) nên hàm trên quan trọng hơn.
    return "Interactive mode not optimized for generic text yet."

def translate_file(input_text, progress_callback=None, include_english=True, source_lang='zh', target_lang='vi', pinyin_style='tone_marks', translation_mode="Standard Translation", processed_words=None):
    chunks = split_sentence(input_text)
    total = len(chunks)
    html = ""
    
    with ThreadPoolExecutor(max_workers=5) as ex:
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
    
    for res in results:
        html += create_html_block(res, include_english)
        
    with open('template.html', 'r', encoding='utf-8') as f:
        template = f.read()
    return template.replace('{{content}}', html)
