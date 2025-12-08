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

def split_sentence(text: str) -> List[str]:
    """Split text into sentences or meaningful chunks"""
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text.strip())

    # Segmentation logic (Giữ nguyên)
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
                chunk.count('"') + chunk.count('"')
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


def translate_text(text, target_lang, include_english): # <--- Cần thêm tham số include_english cho khớp với Translator mới
    """Translate text using Translator class (Gemini)"""
    if 'translator' not in st.session_state:
        from translator import Translator
        st.session_state.translator = Translator()
    
    try:
        # Gọi hàm translate_text mới trong translator.py (Gemini)
        # Hàm này trả về string (có thể là 1 dòng hoặc 2 dòng nếu có tiếng Anh)
        translation = st.session_state.translator.translate_text(text, target_lang, include_english)
        return translation
    except Exception as e:
        print(f"Translation error: {str(e)}")
        return ""


def process_chunk(chunk: str, index: int, executor: ThreadPoolExecutor, include_english: bool, second_language: str, pinyin_style: str = 'tone_marks') -> tuple:
    try:
        # Get pinyin
        pinyin = convert_to_pinyin(chunk, pinyin_style)

        # Get translations (Gemini trả về cả cục)
        full_translation = translate_text(chunk, second_language, include_english)
        
        # Tách dòng để lấy English và Ngôn ngữ đích
        parts = full_translation.split('\n')
        parts = [p.strip() for p in parts if p.strip()] # Lọc dòng trống
        
        translations = []
        if include_english and second_language != 'en':
            # Giả định Gemini trả về: Dòng 1 = Ngôn ngữ đích, Dòng 2 = English
            # (Hoặc ngược lại tuỳ vào prompt, nhưng translator.py đã fix prompt chuẩn)
            if len(parts) >= 2:
                # English thường ở dòng 2 theo prompt mới
                english = parts[1] 
                second_trans = parts[0]
            elif len(parts) == 1:
                second_trans = parts[0]
                english = "[Missing Eng]"
            else:
                english = "..."
                second_trans = "..."
                
            translations.append(english)
            translations.append(second_trans)
            
        else:
            # Chỉ 1 ngôn ngữ
            second_trans = parts[0] if len(parts) > 0 else "..."
            translations.append(second_trans)

        return (index, chunk, pinyin, *translations)

    except Exception as e:
        print(f"\nError processing chunk {index}: {e}")
        error_translations = ["[Translation Error]"] * (1 + int(include_english))
        return (index, chunk, "[Pinyin Error]", *error_translations)


def create_html_block(results: tuple, include_english: bool) -> str:
    # Nút phát âm (Dùng logic cũ nhưng trỏ đến hàm speakSentence mới trong HTML)
    speak_button = '''
        <button class="speak-button" onclick="speakSentence(this.parentElement.textContent.replace('🔊', ''))">
            <svg viewBox="0 0 24 24">
                <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>
            </svg>
        </button>
    '''
    
    if include_english:
        # Giải nén kết quả (Có thêm English)
        try:
            index, chunk, pinyin, english, second = results
        except ValueError:
             # Fallback nếu số lượng biến không khớp
             index, chunk, pinyin = results[0], results[1], results[2]
             english, second = "Error", "Error"

        return f'''
            <div class="sentence-part responsive">
                <div class="original">{index + 1}. {chunk}{speak_button}</div>
                <div class="pinyin">{pinyin}</div>
                <div class="english">{english}</div>
                <div class="second-language">{second}</div>
            </div>
        '''
    else:
        # Giải nén kết quả (Không có English)
        try:
            index, chunk, pinyin, second = results
        except ValueError:
             index, chunk, pinyin = results[0], results[1], results[2]
             second = "Error"

        return f'''
            <div class="sentence-part responsive">
                <div class="original">{index + 1}. {chunk}{speak_button}</div>
                <div class="pinyin">{pinyin}</div>
                <div class="second-language">{second}</div>
            </div>
        '''


def process_text(file_path, include_english=True, second_language="vi", pinyin_style='tone_marks'):
    """Process text with language options and pinyin style"""
    # (Giữ nguyên logic cũ, chỉ thay đổi luồng ThreadPool)
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    with open('template.html', 'r', encoding='utf-8') as template_file:
        html_content = template_file.read()

    translation_content = ''
    global_index = 0
    max_workers = 5 # Tăng worker lên chút vì Gemini nhanh hơn Azure

    all_results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []

        for line_idx, line in enumerate(lines):
            if line.strip():
                chunks = split_sentence(line.strip())
                for chunk_idx, chunk in enumerate(chunks):
                    future = executor.submit(
                        process_chunk,
                        chunk,
                        global_index,
                        executor,
                        include_english,
                        second_language,
                        pinyin_style
                    )
                    futures.append((global_index, line_idx, chunk_idx, future))
                    global_index += 1

        for global_idx, line_idx, chunk_idx, future in futures:
            try:
                result = future.result(timeout=60)
                all_results.append((line_idx, chunk_idx, result))
            except Exception as e:
                print(f"\nError getting result: {e}")
                continue

    all_results.sort(key=lambda x: (x[0], x[1]))

    current_line = -1
    for line_idx, chunk_idx, result in all_results:
        if line_idx != current_line:
            if current_line != -1:
                translation_content += '</div>'
            translation_content += '<div class="translation-block">'
            current_line = line_idx

        translation_content += create_html_block(result, include_english)

    if all_results:
        translation_content += '</div>'

    html_content = html_content.replace('{{content}}', translation_content)
    return html_content


def process_interactive_chunk(chunk: str, index: int, executor: ThreadPoolExecutor, include_english: bool, second_language: str, pinyin_style: str = 'tone_marks') -> tuple:
    """Process chunk for interactive word-by-word translation"""
    try:
        if 'translator' not in st.session_state:
            from translator import Translator
            st.session_state.translator = Translator()
        
        # Gọi hàm Gemini mới
        processed_words = st.session_state.translator.process_chinese_text(chunk, second_language)
        if not processed_words:
            return (index, chunk, [])
            
        return (index, chunk, processed_words)

    except Exception as e:
        print(f"\nError processing interactive chunk {index}: {str(e)}")
        return (index, chunk, [])

def create_interactive_html_block(results: tuple, include_english: bool) -> str:
    """Create HTML for interactive word-by-word translation"""
    # (Giữ nguyên logic cũ, chỉ thay đổi cách lấy dữ liệu từ JSON)
    chunk, word_data = results
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
            if word_data.get('translations'):
                tooltip_content = f"{word_data['pinyin']}\n{word_data['translations'][0]}" # Lấy nghĩa đầu tiên
                content_html += f'''
                    <span class="interactive-word" 
                          onclick="speak('{word_data['word']}')"
                          data-tooltip="{tooltip_content}">
                        {word_data['word']}
                    </span>'''
            else:
                content_html += f'<span class="non-chinese">{word_data["word"]}</span>'
        content_html += '</p>'
    
    content_html += '</div>'
    return content_html

def translate_file(input_text: str, progress_callback=None, include_english=True, 
                  second_language="vi", pinyin_style='tone_marks', 
                  translation_mode="Standard Translation", processed_words=None):
    """Translate text with progress updates"""
    try:
        text = input_text.strip()
        
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
            # Standard Mode
            chunks = split_sentence(text)
            total_chunks = len(chunks)
            chunks_processed = 0
            translation_content = ""
            
            if progress_callback: progress_callback(0)

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
                        second_language,
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
                        continue

            all_results.sort(key=lambda x: x[0])
            
            for result in all_results:
                translation_content += create_html_block(result, include_english)

            with open('template.html', 'r', encoding='utf-8') as template_file:
                html_content = template_file.read()
                
            if progress_callback: progress_callback(100)
            return html_content.replace('{{content}}', translation_content)

    except Exception as e:
        print(f"Translation error: {str(e)}")
        raise

# (Phần main() giữ nguyên)
def main():
    if len(sys.argv) != 2:
        print("Usage: python tranlate_book.py <input_file>")
        sys.exit(1)
    input_file = sys.argv[1]
    if not os.path.exists(input_file):
        print(f"Error: File '{input_file}' not found")
        sys.exit(1)
    translate_file(input_file)

if __name__ == "__main__":
    main()
