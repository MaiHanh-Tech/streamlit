import pypinyin
import re
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Tuple, List
from functools import partial
from tqdm import tqdm
import sys
import time
import random
import streamlit as st

def split_sentence(text: str) -> List[str]:
    """Tách đoạn văn thành các câu nhỏ hơn để dịch"""
    text = re.sub(r'\s+', ' ', text.strip())
    # Tách câu dựa trên cả dấu chấm câu tiếng Anh và tiếng Trung
    pattern = r'([。！？，：；.!?,][」"』\'）)]*(?:\s*[「""『\'（(]*)?)'
    splits = re.split(pattern, text)
    chunks = []
    current = ""
    for s in splits:
        if not s: continue
        # Gom các câu quá ngắn lại để dịch một thể cho mượt (dưới 100 ký tự)
        if len(current) + len(s) < 100: 
            current += s
        else:
            chunks.append(current)
            current = s
    if current: chunks.append(current)
    return [chunk.strip() for chunk in chunks if chunk.strip()]

def convert_to_pinyin(text, style='tone_marks'):
    """Chuyển đổi sang Pinyin (Chỉ dùng cho tiếng Trung)"""
    try:
        p_style = pypinyin.TONE3 if style == 'tone_numbers' else pypinyin.TONE
        return ' '.join([i[0] for i in pypinyin.pinyin(text, style=p_style)])
    except: return ""

def translate_text(text, source_lang, target_lang, include_eng):
    """Gọi hàm dịch từ Translator (Gemini)"""
    if 'translator' not in st.session_state:
        from translator import Translator
        st.session_state.translator = Translator()
    # Gọi hàm translate_text mới trong translator.py
    return st.session_state.translator.translate_text(text, source_lang, target_lang, include_eng)

def process_chunk(chunk, index, executor, include_english, source_code, target_code, pinyin_style):
    """Xử lý từng đoạn nhỏ: Pinyin + Dịch + Tách dòng"""
    time.sleep(random.uniform(0.1, 0.3)) # Nghỉ xíu tránh spam API
    try:
        # 1. Pinyin (Chỉ hiện nếu nguồn là Trung - zh)
        pinyin_text = convert_to_pinyin(chunk, pinyin_style) if source_code == 'zh' else ''

        # 2. Xử lý Dịch
        # LOGIC MỚI: Nếu Nguồn là Anh (en), ta TỰ LẤY nguồn làm bản dịch Anh
        if source_code == 'en' and include_english:
            # Chỉ bảo AI dịch sang Target (Vd: Việt)
            target_val = translate_text(chunk, source_code, target_code, False).strip()
            english_val = chunk # Lấy gốc làm Anh luôn
            
            return (index, chunk, pinyin_text, english_val, target_val)
            
        else:
            # Logic cũ cho các ngôn ngữ khác (AI trả về 2 dòng nếu cần)
            full_trans = translate_text(chunk, source_code, target_code, include_english)
            parts = [p.strip() for p in full_trans.split('\n') if p.strip()]
            
            if include_english and target_code != 'en':
                # Hy vọng AI trả về: Dòng 1 Target, Dòng 2 English
                target_val = parts[0] if len(parts) > 0 else "..."
                english_val = parts[1] if len(parts) > 1 else "..."
                return (index, chunk, pinyin_text, english_val, target_val)
            else:
                # Chỉ lấy 1 dòng bản dịch chính
                target_val = parts[0] if len(parts) > 0 else "..."
                return (index, chunk, pinyin_text, target_val)

    except Exception as e:
        error_val = f"[Error: {str(e)}]"
        return (index, chunk, "", error_val, error_val) if include_english else (index, chunk, "", error_val)

def create_html_block(results, include_english):
    """Tạo khối HTML hiển thị kết quả (Giao diện Standard)"""
    # Nút phát âm (Loa)
    speak_btn = '''<button class="speak-button" onclick="speakSentence(this.parentElement.textContent.replace('🔊', ''))"><svg viewBox="0 0 24 24"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg></button>'''
    
    if include_english:
        # Nếu có tiếng Anh: Index, Gốc, Pinyin, Anh, Đích
        idx, orig, pin, eng, sec = results
        # Ẩn dòng Pinyin nếu trống (khi nguồn không phải Trung)
        pinyin_div = f'<div class="pinyin">{pin}</div>' if pin else ''
        
        return f'''
            <div class="sentence-part responsive">
                <div class="original">{idx+1}. {orig}{speak_btn}</div>
                {pinyin_div}
                <div class="english">{eng}</div>
                <div class="second-language">{sec}</div>
            </div>
        '''
    else:
        # Nếu không có tiếng Anh: Index, Gốc, Pinyin, Đích
        idx, orig, pin, sec = results
        pinyin_div = f'<div class="pinyin">{pin}</div>' if pin else ''
        
        return f'''
            <div class="sentence-part responsive">
                <div class="original">{idx+1}. {orig}{speak_btn}</div>
                {pinyin_div}
                <div class="second-language">{sec}</div>
            </div>
        '''

def create_interactive_html_block(results: tuple, include_english: bool) -> str:
    """Tạo HTML cho chế độ Interactive (Click từng từ)"""
    chunk_original, word_data = results
    
    content_html = '<div class="interactive-text">'
    current_paragraph = []
    paragraphs = []
    
    # Gom nhóm từ thành đoạn văn
    for word in word_data:
        if word.get('word') == '\n':
            if current_paragraph:
                paragraphs.append(current_paragraph)
                current_paragraph = []
        else:
            current_paragraph.append(word)
    
    if current_paragraph:
        paragraphs.append(current_paragraph)
    
    # Tạo HTML
    for paragraph in paragraphs:
        content_html += '<p class="interactive-paragraph">'
        for word_data in paragraph:
            
            translations_list = word_data.get('translations', [])
            tooltip_content = ""
            if translations_list:
                tooltip_content = "\n".join(translations_list)
                
            pinyin_text = word_data.get('pinyin', '')
            
            if word_data.get('word') and word_data.get('word').strip():
                content_html += f'''
                    <span class="interactive-word" 
                          onclick="speak('{word_data['word']}')"
                          data-tooltip="{pinyin_text}&#10;{tooltip_content}">
                        {word_data['word']}
                    </span>'''
            else:
                content_html += f'<span class="non-chinese">{word_data["word"]}</span>'
        content_html += '</p>'
    
    content_html += '</div>'
    return content_html

def translate_file(input_text, progress_callback=None, include_english=True, source_lang='zh', target_lang='vi', pinyin_style='tone_marks', translation_mode="Standard Translation", processed_words=None):
    """Hàm chính điều phối quá trình dịch"""
    try:
        text = input_text.strip()
        
        # 1. Chế độ Interactive (Từ vựng)
        if translation_mode == "Interactive Word-by-Word" and processed_words is not None:
            with open('template.html', 'r', encoding='utf-8') as template_file:
                html_content = template_file.read()
            
            if progress_callback: progress_callback(100)
            
            translation_content = create_interactive_html_block(
                (text, processed_words),
                include_english
            )
            return html_content.replace('{{content}}', translation_content)
            
        # 2. Chế độ Standard (Dịch câu/đoạn)
        else:
            chunks = split_sentence(text)
            total_chunks = len(chunks)
            chunks_processed = 0
            translation_content = ""
            
            if progress_callback: progress_callback(0)

            # Chạy đa luồng (5 luồng cùng lúc) để nhanh hơn
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = []
                for index, chunk in enumerate(chunks):
                    future = executor.submit(
                        process_chunk,
                        chunk,
                        index,
                        executor,
                        include_english,
                        source_lang, 
                        target_lang, 
                        pinyin_style
                    )
                    futures.append(future)

                all_results = []
                for future in futures:
                    try:
                        result = future.result(timeout=60)
                        all_results.append(result)
                        chunks_processed += 1
                        if progress_callback:
                            current_progress = min(100, (chunks_processed / total_chunks) * 100)
                            progress_callback(current_progress)
                    except Exception as e:
                        print(f"Error chunk: {e}")
                        continue

            # Sắp xếp lại theo đúng thứ tự câu
            all_results.sort(key=lambda x: x[0])
            
            # Tạo HTML cuối cùng
            for result in all_results:
                translation_content += create_html_block(result, include_english)

            with open('template.html', 'r', encoding='utf-8') as template_file:
                html_content = template_file.read()
                
            if progress_callback: progress_callback(100)
                
            return html_content.replace('{{content}}', translation_content)

    except Exception as e:
        print(f"Translation error: {str(e)}")
        raise
