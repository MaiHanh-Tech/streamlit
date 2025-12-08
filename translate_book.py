import pypinyin
import re
from concurrent.futures import ThreadPoolExecutor
import time
import random
import streamlit as st

def split_sentence(text):
    """Tách câu tiếng Trung (Logic gốc)"""
    text = re.sub(r'\s+', ' ', text.strip())
    pattern = r'([。！？，：；.!?,][」"』\'）)]*(?:\s*[「""『\'（(]*)?)'
    splits = re.re.split(pattern, text)
    chunks = []
    current = ""
    for s in splits:
        if not s: continue
        if len(current) + len(s) < 100: current += s
        else:
            chunks.append(current)
            current = s
    if current: chunks.append(current)
    return [c.strip() for c in chunks if c.strip()]

def convert_to_pinyin(text, style='tone_marks'):
    """Chuyển đổi Pinyin"""
    try:
        p_style = pypinyin.TONE3 if style == 'tone_numbers' else pypinyin.TONE
        return ' '.join([i[0] for i in pypinyin.pinyin(text, style=p_style)])
    except: return ""

def translate_text(text, target, include_eng):
    """Gọi hàm dịch từ Translator (Gemini)"""
    if 'translator' not in st.session_state:
        from translator import Translator
        st.session_state.translator = Translator()
    return st.session_state.translator.translate_text(text, target, include_eng)

def process_chunk(chunk, index, executor, include_english, target_code, pinyin_style):
    """Xử lý dịch từng câu"""
    time.sleep(random.uniform(0.1, 0.3))
    try:
        # Pinyin (Luôn tạo vì App chuyên Trung)
        pinyin_text = convert_to_pinyin(chunk, pinyin_style)
        
        # Dịch
        full_trans = translate_text(chunk, target_code, include_english)
        
        # Tách kết quả (Gemini trả về: Dòng 1 Đích, Dòng 2 Anh)
        parts = [p.strip() for p in full_trans.split('\n') if p.strip()]
        
        if include_english and target_code != 'en':
            target_val = parts[0] if len(parts) > 0 else "..."
            eng_val = parts[1] if len(parts) > 1 else "..."
            return (index, chunk, pinyin_text, eng_val, target_val)
        else:
            target_val = parts[0] if len(parts) > 0 else "..."
            return (index, chunk, pinyin_text, target_val)
            
    except Exception as e:
        err = f"[Err: {e}]"
        if include_english: return (index, chunk, "", err, err)
        else: return (index, chunk, "", err)

# --- SỬA Ở ĐÂY: KHÔI PHỤC MÀU SẮC GỐC ---
def create_html_block(results, include_english):
    speak_btn = '''<button class="speak-button" onclick="speakSentence(this.parentElement.textContent.replace('🔊', ''))"><svg viewBox="0 0 24 24"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg></button>'''
    
    # CSS Màu sắc (Dựa trên ảnh gốc của chị)
    COLOR_PINYIN = '#FFD700' # Vàng Gold
    COLOR_ENGLISH = '#90EE90' # Xanh lá nhạt
    COLOR_VIETNAMESE = '#FFB6C1' # Hồng nhạt
    
    # Logic CSS (Giữ nguyên)
    style_pinyin = f'style="color: {COLOR_PINYIN};"'
    style_english = f'style="color: {COLOR_ENGLISH};"'
    style_second = f'style="color: {COLOR_VIETNAMESE};"'
    
    if include_english:
        idx, orig, pin, eng, sec = results
        pin_html = f'<div class="pinyin" {style_pinyin}>{pin}</div>'
        return f'''
            <div class="sentence-part responsive">
                <div class="original">{idx+1}. {orig}{speak_btn}</div>
                {pin_html}
                <div class="english" {style_english}>{eng}</div>
                <div class="second-language" {style_second}>{sec}</div>
            </div>
        '''
    else:
        idx, orig, pin, sec = results
        pin_html = f'<div class="pinyin" {style_pinyin}>{pin}</div>'
        return f'''
            <div class="sentence-part responsive">
                <div class="original">{idx+1}. {orig}{speak_btn}</div>
                {pin_html}
                <div class="second-language" {style_second}>{sec}</div>
            </div>
        '''

def create_interactive_html_block(results, include_english):
    # Lấy lại logic Interactive cũ
    text, word_data = results
    html = '<div class="interactive-text"><p class="interactive-paragraph">'
    for w in word_data:
        if w.get('translations'):
            tooltip = f"{w['pinyin']}\n{w['translations'][0]}"
            html += f'<span class="interactive-word" onclick="speak(\'{w["word"]}\')" data-tooltip="{tooltip}">{w["word"]}</span>'
        else:
            html += f'<span class="non-chinese">{w.get("word", "")}</span>'
    html += '</p></div>'
    return html

def translate_file(input_text, progress_callback=None, include_english=True, target_lang='vi', pinyin_style='tone_marks', translation_mode="Standard Translation", processed_words=None):
    if translation_mode == "Interactive Word-by-Word":
        with open('template.html', 'r', encoding='utf-8') as f: template = f.read()
        content = create_interactive_html_block((input_text, processed_words), include_english)
        return template.replace('{{content}}', content)
        
    chunks = split_sentence(input_text)
    total = len(chunks)
    html = ""
    
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = []
        for i, chunk in enumerate(chunks):
            futures.append(ex.submit(process_chunk, chunk, i, ex, include_english, target_lang, pinyin_style))
        
        results = []
        done = 0
        for f in futures:
            try: results.append(f.result())
            except: pass
            done += 1
            if progress_callback: progress_callback(done/total * 100)
            
    results.sort(key=lambda x: x[0])
    for res in results: html += create_html_block(res, include_english)
        
    with open('template.html', 'r', encoding='utf-8') as f: template = f.read()
    return template.replace('{{content}}', html)
