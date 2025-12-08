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
    """Split text into sentences or meaningful chunks"""
    text = re.sub(r'\s+', ' ', text.strip())

    # Segmentation logic (Giữ nguyên logic gốc của anh ấy)
    pattern = r'([。！？，：；.!?,][」"』\'）)]*(?:\s*[「""『\'（(]*)?)'
    splits = re.split(pattern, text)

    chunks = []
    current_chunk = ""
    min_length = 20
    quote_count = 0 

    for i in range(0, len(splits)-1, 2):
        if splits[i]:
            chunk = splits[i] + (splits[i+1] if i+1 < len(splits) else '')

            quote_count += chunk.count('"') + \
                chunk.count('"') + chunk.count('“') + chunk.count('”')
            quote_count += chunk.count('「') + chunk.count('」')
            quote_count += chunk.count('『') + chunk.count('』')

            if quote_count % 2 == 1 or (len(current_chunk) + len(chunk) < min_length and i < len(splits)-2):
                current_chunk += chunk
            else:
                if current_chunk:
                    chunks.append(current_chunk + chunk)
                    current_chunk = ""
                else:
                    chunks.append(chunk)
                quote_count = 0 

    if splits[-1] or current_chunk:
        last_chunk = splits[-1] if splits[-1] else ""
        if current_chunk:
            chunks.append(current_chunk + last_chunk)
        elif last_chunk:
            chunks.append(last_chunk)

    return [chunk.strip() for chunk in chunks if chunk.strip()]


def convert_to_pinyin(text: str, style: str = 'tone_marks') -> str:
    """Convert Chinese text to pinyin with specified style"""
    try:
        if style == 'tone_numbers':
            pinyin_style = pypinyin.TONE3
        else:
            pinyin_style = pypinyin.TONE

        pinyin_list = pypinyin.pinyin(text, style=pinyin_style)
        return ' '.join([item[0] for item in pinyin_list])
    except Exception as e:
        return "[Pinyin Error]"


def translate_text(text, source_lang, target_lang, include_english): # <--- ĐÃ SỬA
    """Translate text using Translator class (Gemini)"""
    if 'translator' not in st.session_state:
        from translator import Translator
        st.session_state.translator = Translator()
    
    try:
        # Gọi hàm translate_text đã được sửa trong translator.py
        translation = st.session_state.translator.translate_text(text, source_lang, target_lang, include_english)
        return translation
    except Exception as e:
        print(f"Translation error: {str(e)}")
        return ""


def process_chunk(chunk: str, index: int, executor: ThreadPoolExecutor, include_english: bool, source_language: str, target_language: str, pinyin_style: str = 'tone_marks') -> tuple: # <--- ĐÃ SỬA
    """Xử lý từng đoạn nhỏ (Standard Translation)"""
    time.sleep(random.uniform(0.1, 0.5)) 
    
    try:
        # Pinyin chỉ chạy nếu Source là Tiếng Trung (theo App gốc)
        pinyin_text = convert_to_pinyin(chunk, pinyin_style) if source_language == 'Chinese' else ''

        # Get translations (Gemini sẽ trả về cả 2 bản dịch nếu có)
        full_translation = translate_text(chunk, source_language, target_language, include_english)
        
        # Logic tách English và Ngôn ngữ đích
        translations = full_translation.split('\n')
        
        final_translations = []
        
        if include_english and target_language != 'English':
            # Giả định câu đầu là ngôn ngữ đích, câu sau là English (Do Gemini trả về)
            final_translations.append(translations[1] if len(translations) > 1 else "[English Trans Error]")
            final_translations.append(translations[0] if len(translations) > 0 else "[Target Lang Trans Error]")
        else:
            # Chỉ lấy bản dịch chính
            final_translations.append(translations[0] if len(translations) > 0 else "[Target Lang Trans Error]")
        
        # Index, Original, Pinyin, *Translations
        return (index, chunk, pinyin_text, *final_translations)

    except Exception as e:
        error_translations = ["[Translation Error]"] * (1 + int(include_english))
        return (index, chunk, "[Pinyin Error]", *error_translations)


def create_html_block(results: tuple, include_english: bool) -> str:
    """Tạo HTML block cho Standard Translation"""
    speak_button = '''
        <button class="speak-button" onclick="speakSentence(this.parentElement.textContent.replace('🔊', ''))">
            <svg viewBox="0 0 24 24">
                <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>
            </svg>
        </button>
    '''
    
    if include_english:
        index, chunk, pinyin, english, second = results
        return f'''
            <div class="sentence-part responsive">
                <div class="original">{index + 1}. {chunk}{speak_button}</div>
                <div class="pinyin">{pinyin}</div>
                <div class="english">{english}</div>
                <div class="second-language">{second}</div>
            </div>
        '''
    else:
        index, chunk, pinyin, second = results
        return f'''
            <div class="sentence-part responsive">
                <div class="original">{index + 1}. {chunk}{speak_button}</div>
                <div class="pinyin">{pinyin}</div>
                <div class="second-language">{second}</div>
            </div>
        '''


def create_interactive_html_block(results: tuple, include_english: bool) -> str:
    """Tạo HTML block cho Interactive Translation"""
    chunk_original, word_data = results
    
    content_html = '<div class="interactive-text">'
    
    current_paragraph = []
    paragraphs = []
    
    for word in word_data:
        if word.get('word') == '\n':
            if current_paragraph:
                paragraphs.append(current_paragraph)
                current_paragraph = []
        else:
            current_paragraph.append(word)
    
    if current_paragraph:
        paragraphs.append(current_paragraph)
    
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


def translate_file(input_text: str, progress_callback=None, include_english=True, 
                  source_language="Chinese", target_language="Vietnamese", pinyin_style='tone_marks', 
                  translation_mode="Standard Translation", processed_words=None):
    """Translate text with progress updates"""
    try:
        text = input_text.strip()
        
        if translation_mode == "Interactive Word-by-Word" and processed_words is not None:
            # Interactive mode
            with open('template.html', 'r', encoding='utf-8') as template_file:
                html_content = template_file.read()
            
            if progress_callback:
                progress_callback(100)
            
            translation_content = create_interactive_html_block(
                (text, processed_words),
                include_english
            )
            
            return html_content.replace('{{content}}', translation_content)
            
        else:
            # Standard translation mode
            chunks = split_sentence(text)
            total_chunks = len(chunks)
            chunks_processed = 0

            translation_content = ""
            
            if progress_callback:
                progress_callback(0)

            max_workers = 5
            all_results = []
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                
                for index, chunk in enumerate(chunks):
                    future = executor.submit(
                        process_chunk,
                        chunk,
                        index,
                        executor,
                        include_english,
                        source_language, # Đã sửa
                        target_language, # Đã sửa
                        pinyin_style
                    )
                    futures.append((index, future))

                for index, future in futures:
                    try:
                        result = future.result(timeout=60)
                        all_results.append(result)
                        chunks_processed += 1
                        if progress_callback:
                            current_progress = min(100, (chunks_processed / total_chunks) * 100)
                            progress_callback(current_progress)
                    except Exception as e:
                        error_translations = ["[Translation Error]"] * (1 + int(include_english))
                        all_results.append((index, chunks[index], "[Pinyin Error]", *error_translations))
                        chunks_processed += 1
                        if progress_callback:
                            current_progress = min(100, (chunks_processed / total_chunks) * 100)
                            progress_callback(current_progress)
                        continue

            all_results.sort(key=lambda x: x[0])
            
            for result in all_results:
                translation_content += create_html_block(result, include_english)

            with open('template.html', 'r', encoding='utf-8') as template_file:
                html_content = template_file.read()
                
            if progress_callback:
                progress_callback(100)
                
            return html_content.replace('{{content}}', translation_content)

    except Exception as e:
        raise
