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

    # Pattern considering quotes and punctuation
    pattern = r'([。！？，：；.!?,][」"』\'）)]*(?:\s*[「""『\'（(]*)?)'
    splits = re.split(pattern, text)

    # Merge chunks
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
        print(f"Error converting to pinyin: {e}")
        return "[Pinyin Error]"


def translate_text(text, target_lang):
    """Translate text using the initialized Translator"""
    if 'translator' not in st.session_state:
        from translator import Translator
        st.session_state.translator = Translator()
    
    try:
        translation = st.session_state.translator.translate_text(text, target_lang)
        return translation
    except Exception as e:
        print(f"Translation error: {str(e)}")
        return ""


def process_chunk(chunk: str, index: int, executor: ThreadPoolExecutor, include_english: bool, second_language: str, pinyin_style: str = 'tone_marks') -> tuple:
    try:
        # Get pinyin
        pinyin = convert_to_pinyin(chunk, pinyin_style)

        # Get translations
        translations = []
        
        # --- FIX: Always append to translations list even if result is empty ---
        # This prevents the "expected 5, got 3" error
        
        if include_english:
            english = translate_text(chunk, 'en')
            # Use empty string if None, don't skip appending
            translations.append(english if english else "")

        second_trans = translate_text(chunk, second_language)
        # Use empty string if None, don't skip appending
        translations.append(second_trans if second_trans else "")

        return (index, chunk, pinyin, *translations)

    except Exception as e:
        print(f"\nError processing chunk {index}: {e}")
        # Ensure we return the correct number of error placeholders
        error_count = 1 + (1 if include_english else 0)
        error_translations = ["[Error]"] * error_count
        return (index, chunk, "[Pinyin Error]", *error_translations)


def create_html_block(results: tuple, include_english: bool) -> str:
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


def process_interactive_chunk(chunk: str, index: int, executor: ThreadPoolExecutor, include_english: bool, second_language: str, pinyin_style: str = 'tone_marks') -> tuple:
    """Process chunk for interactive word-by-word translation"""
    try:
        if 'translator' not in st.session_state:
            from translator import Translator
            st.session_state.translator = Translator()
        
        processed_words = st.session_state.translator.process_chinese_text(chunk, second_language)
        if not processed_words:
            return (index, chunk, [])
            
        return (index, chunk, processed_words)

    except Exception as e:
        print(f"\nError processing interactive chunk {index}: {str(e)}")
        return (index, chunk, [])


def create_interactive_html_block(results: tuple, include_english: bool) -> str:
    """Create HTML for interactive word-by-word translation"""
    chunk, word_data = results
    
    content_html = '<div class="interactive-text">'
    
    current_paragraph = []
    paragraphs = []
    
    for word in word_data:
        # Handle dict or Pydantic model dump (both are dicts)
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
        
        if translation_mode == "Interactive Word-by-Word" and processed_words:
            with open('template.html', 'r', encoding='utf-8') as template_file:
                html_content = template_file.read()
            
            if progress_callback:
                progress_callback(0)
            
            translation_content = create_interactive_html_block(
                (text, processed_words),
                include_english
            )
            
            if progress_callback:
                progress_callback(100)
                
            return html_content.replace('{{content}}', translation_content)
        else:
            # Standard translation mode
            chunks = split_sentence(text)
            total_chunks = len(chunks)
            chunks_processed = 0

            translation_content = ""
            
            if progress_callback:
                progress_callback(0)
                print(f"Total chunks: {total_chunks}")

            # Using ThreadPoolExecutor locally in this block for standard translation if needed
            # but simpler to run sequentially or reuse logic.
            # Here we keep it simple calling process_chunk
            
            for chunk in chunks:
                result = process_chunk(
                    chunk, chunks_processed, None, 
                    include_english, second_language, pinyin_style
                )
                
                translation_content += create_html_block(result, include_english)
                
                chunks_processed += 1
                if progress_callback:
                    current_progress = min(100, (chunks_processed / total_chunks) * 100)
                    progress_callback(current_progress)

            with open('template.html', 'r', encoding='utf-8') as template_file:
                html_content = template_file.read()
                
            if progress_callback:
                progress_callback(100)
                
            return html_content.replace('{{content}}', translation_content)

    except Exception as e:
        print(f"Translation error: {str(e)}")
        raise

def main():
    if len(sys.argv) != 2:
        print("Usage: python translate_book.py <input_file>")
        sys.exit(1)

    input_file = sys.argv[1]
    if not os.path.exists(input_file):
        print(f"Error: File '{input_file}' not found")
        sys.exit(1)

    print(translate_file(open(input_file, 'r', encoding='utf-8').read()))


if __name__ == "__main__":
    main()
