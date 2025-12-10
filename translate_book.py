import pypinyin
import re
import os
import sys
import jieba
import streamlit as st
# Import Translator class
from translator import Translator

def split_sentence(text: str) -> list:
    """Split text into sentences"""
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
    try:
        pinyin_style = pypinyin.TONE3 if style == 'tone_numbers' else pypinyin.TONE
        pinyin_list = pypinyin.pinyin(text, style=pinyin_style)
        return ' '.join([item[0] for item in pinyin_list])
    except:
        return ""


def process_chunk(chunk: str, index: int, translator_instance, include_english: bool, second_language: str, pinyin_style: str = 'tone_marks') -> tuple:
    try:
        # Pinyin
        pinyin = convert_to_pinyin(chunk, pinyin_style)

        # Translation
        translations = []
        
        # English
        if include_english:
            english = translator_instance.translate_text(chunk, 'en')
            translations.append(english)

        # Second Language
        second_trans = translator_instance.translate_text(chunk, second_language)
        translations.append(second_trans)

        return (index, chunk, pinyin, *translations)

    except Exception as e:
        print(f"Error chunk {index}: {e}")
        # Trả về lỗi rõ ràng để hiển thị
        error_msg = f"[Sys Error: {str(e)}]"
        count = 2 if include_english else 1
        return (index, chunk, pinyin, *([error_msg] * count))


def create_html_block(results: tuple, include_english: bool) -> str:
    speak_button = '''<button class="speak-button" onclick="speakSentence(this.parentElement.textContent.replace('🔊', ''))"><svg viewBox="0 0 24 24"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg></button>'''
    
    # Safe Unpacking
    try:
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
    except Exception:
        return f"<div>Error displaying block {results[1]}</div>"


def create_interactive_html_block(results: tuple, include_english: bool) -> str:
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
    if current_paragraph: paragraphs.append(current_paragraph)
    
    for paragraph in paragraphs:
        content_html += '<p class="interactive-paragraph">'
        for word_data in paragraph:
            if word_data.get('translations'):
                tooltip = f"{word_data['pinyin']}\n{word_data['translations'][-1]}"
                content_html += f'<span class="interactive-word" onclick="speak(\'{word_data["word"]}\')" data-tooltip="{tooltip}">{word_data["word"]}</span>'
            else:
                content_html += f'<span class="non-chinese">{word_data.get("word", "")}</span>'
        content_html += '</p>'
    
    return content_html + '</div>'


def translate_file(input_text: str, progress_callback=None, include_english=True, 
                  second_language="vi", pinyin_style='tone_marks', 
                  translation_mode="Standard Translation", processed_words=None):
    try:
        text = input_text.strip()
        
        # --- QUAN TRỌNG: Khởi tạo Translator mới 100% ở đây ---
        # Bỏ qua session_state để tránh cache lỗi cũ
        translator_instance = Translator()
        # ----------------------------------------------------

        if translation_mode == "Interactive Word-by-Word" and processed_words:
            with open('template.html', 'r', encoding='utf-8') as f: html = f.read()
            content = create_interactive_html_block((text, processed_words), include_english)
            return html.replace('{{content}}', content)
        
        else:
            chunks = split_sentence(text)
            total = len(chunks)
            translation_content = ""
            
            if progress_callback: progress_callback(0)

            # Chạy tuần tự để đảm bảo ổn định (Sequential processing)
            for i, chunk in enumerate(chunks):
                result = process_chunk(
                    chunk, i, 
                    translator_instance, 
                    include_english, second_language, pinyin_style
                )
                translation_content += create_html_block(result, include_english)
                
                if progress_callback:
                    progress_callback(min(100, ((i+1)/total)*100))

            with open('template.html', 'r', encoding='utf-8') as f: html = f.read()
            return html.replace('{{content}}', translation_content)

    except Exception as e:
        return f"<h3>Critical Error: {str(e)}</h3>"

if __name__ == "__main__":
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        print(translate_file(open(sys.argv[1], 'r', encoding='utf-8').read()))
