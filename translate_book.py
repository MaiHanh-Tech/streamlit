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
import jieba
import streamlit as st

# Import Translator class để type hinting hoặc khởi tạo nếu cần
from translator import Translator

def split_sentence(text: str) -> List[str]:
    """Split text into sentences or meaningful chunks"""
    text = re.sub(r'\s+', ' ', text.strip())
    pattern = r'([。！？，：；.!?,][」"』\'）)]*(?:\s*[「""『\'（(]*)?)'
    splits = re.split(pattern, text)

    chunks = []
    current_chunk = ""
    min_length = 20
    quote_count = 0

    for i in range(0, len(splits)-1, 2):
        if splits[i]:
            chunk = splits[i] + (splits[i+1] if i+1 < len(splits) else '')
            quote_count += chunk.count('"') + chunk.count('"') + chunk.count('"')
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
    """Convert Chinese text to pinyin"""
    try:
        if style == 'tone_numbers':
            pinyin_style = pypinyin.TONE3
        else:
            pinyin_style = pypinyin.TONE
        pinyin_list = pypinyin.pinyin(text, style=pinyin_style)
        return ' '.join([item[0] for item in pinyin_list])
    except Exception as e:
        print(f"Error converting to pinyin: {e}")
        return "[Pinyin Error]"


# --- SỬA ĐỔI QUAN TRỌNG: Hàm này nhận translator instance trực tiếp ---
def translate_text_with_instance(text: str, target_lang: str, translator_instance) -> str:
    """Translate using a passed translator instance (Thread-safe way)"""
    try:
        # Gọi trực tiếp instance được truyền vào, không qua st.session_state
        return translator_instance.translate_text(text, target_lang)
    except Exception as e:
        print(f"Translation error for '{text}': {str(e)}")
        return ""


# --- SỬA ĐỔI QUAN TRỌNG: Nhận translator từ bên ngoài ---
def process_chunk(chunk: str, index: int, translator_instance, include_english: bool, second_language: str, pinyin_style: str = 'tone_marks') -> tuple:
    try:
        # 1. Pinyin
        pinyin = convert_to_pinyin(chunk, pinyin_style)

        # 2. Translation
        translations = []
        
        # English
        if include_english:
            if translator_instance:
                english = translate_text_with_instance(chunk, 'en', translator_instance)
            else:
                english = ""
            translations.append(english if english else "")

        # Second Language (Vietnamese, etc.)
        if translator_instance:
            second_trans = translate_text_with_instance(chunk, second_language, translator_instance)
        else:
            second_trans = ""
        translations.append(second_trans if second_trans else "")

        return (index, chunk, pinyin, *translations)

    except Exception as e:
        print(f"\nError processing chunk {index}: {e}")
        # Return placeholders on error
        error_count = 1 + (1 if include_english else 0)
        error_translations = [""] * error_count
        return (index, chunk, "[Pinyin Error]", *error_translations)


def create_html_block(results: tuple, include_english: bool) -> str:
    speak_button = '''
        <button class="speak-button" onclick="speakSentence(this.parentElement.textContent.replace('🔊', ''))">
            <svg viewBox="0 0 24 24">
                <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>
            </svg>
        </button>
    '''
    
    # Unpack safely
    if include_english:
        if len(results) >= 5:
            index, chunk, pinyin, english, second = results
        else:
            # Fallback safe unpack
            index, chunk, pinyin = results[0], results[1], results[2]
            english, second = "", ""
            
        return f'''
            <div class="sentence-part responsive">
                <div class="original">{index + 1}. {chunk}{speak_button}</div>
                <div class="pinyin">{pinyin}</div>
                <div class="english">{english}</div>
                <div class="second-language">{second}</div>
            </div>
        '''
    else:
        if len(results) >= 4:
            index, chunk, pinyin, second = results
        else:
             # Fallback safe unpack
            index, chunk, pinyin = results[0], results[1], results[2]
            second = ""

        return f'''
            <div class="sentence-part responsive">
                <div class="original">{index + 1}. {chunk}{speak_button}</div>
                <div class="pinyin">{pinyin}</div>
                <div class="second-language">{second}</div>
            </div>
        '''


def create_interactive_html_block(results: tuple, include_english: bool) -> str:
    """Create HTML for interactive word-by-word translation"""
    chunk, word_data = results
    
    content_html = '<div class="interactive-text">'
    
    current_paragraph = []
    paragraphs = []
    
    for word in word_data:
        if isinstance(word, dict) and word.get('word') == '\n':
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
            if word_data.get('translations'):
                tooltip_content = f"{word_data['pinyin']}\n{word_data['translations'][-1]}"
                content_html += f'''
                    <span class="interactive-word" 
                          onclick="speak('{word_data['word']}')"
                          data-tooltip="{tooltip_content}">
                        {word_data['word']}
                    </span>'''
            else:
                content_html += f'<span class="non-chinese">{word_data.get("word", "")}</span>'
        content_html += '</p>'
    
    content_html += '</div>'
    return content_html


def translate_file(input_text: str, progress_callback=None, include_english=True, 
                  second_language="vi", pinyin_style='tone_marks', 
                  translation_mode="Standard Translation", processed_words=None):
    """Translate text with progress updates"""
    try:
        text = input_text.strip()
        
        # --- SỬA ĐỔI QUAN TRỌNG: Lấy translator instance ở Luồng Chính (Main Thread) ---
        translator_instance = None
        if 'translator' in st.session_state:
            translator_instance = st.session_state.translator
        else:
            # Fallback init if not found (hiếm khi xảy ra nếu đã init ở app.py)
            translator_instance = Translator()
        # -------------------------------------------------------------------------------

        if translation_mode == "Interactive Word-by-Word" and processed_words:
            with open('template.html', 'r', encoding='utf-8') as template_file:
                html_content = template_file.read()
            
            if progress_callback: progress_callback(0)
            
            translation_content = create_interactive_html_block(
                (text, processed_words),
                include_english
            )
            
            if progress_callback: progress_callback(100)
            return html_content.replace('{{content}}', translation_content)
        
        else:
            # Standard translation mode
            chunks = split_sentence(text)
            total_chunks = len(chunks)
            chunks_processed = 0
            translation_content = ""
            
            if progress_callback:
                progress_callback(0)

            # Sử dụng ThreadPoolExecutor
            # Lưu ý: Cần truyền translator_instance vào process_chunk
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = []
                for i, chunk in enumerate(chunks):
                    future = executor.submit(
                        process_chunk,
                        chunk, 
                        i, 
                        translator_instance,  # Truyền instance vào đây
                        include_english, 
                        second_language, 
                        pinyin_style
                    )
                    futures.append(future)
                
                # Collect results in order
                results = []
                for future in as_completed(futures):
                    try:
                        res = future.result()
                        results.append(res)
                        chunks_processed += 1
                        if progress_callback:
                            prog = min(100, (chunks_processed / total_chunks) * 100)
                            progress_callback(prog)
                    except Exception as e:
                        print(f"Worker error: {e}")

                # Sort results by index to maintain order
                results.sort(key=lambda x: x[0])
                
                # Build HTML
                for res in results:
                    translation_content += create_html_block(res, include_english)

            with open('template.html', 'r', encoding='utf-8') as template_file:
                html_content = template_file.read()
                
            return html_content.replace('{{content}}', translation_content)

    except Exception as e:
        print(f"Translation error: {str(e)}")
        raise

def main():
    if len(sys.argv) != 2:
        print("Usage: python translate_book.py <input_file>")
        sys.exit(1)

    input_file = sys.argv[1]
    # Note: main() command line usage might fail with st.session_state, 
    # but the web app uses translate_file directly.
    pass

if __name__ == "__main__":
    main()
