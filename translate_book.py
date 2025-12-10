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
    print("Debug: Starting sentence split")  # 添加调试信息

    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text.strip())

    # 更复杂的分割模式，考虑引号和标点的组合
    pattern = r'([。！？，：；.!?,][」"』\'）)]*(?:\s*[「""『\'（(]*)?)'
    splits = re.split(pattern, text)

    print(f"Debug: Initial splits: {len(splits)}")  # 添加调试信息

    # 合并短句和处理引号
    chunks = []
    current_chunk = ""
    min_length = 20
    quote_count = 0  # 跟踪引号状态

    for i in range(0, len(splits)-1, 2):
        if splits[i]:
            chunk = splits[i] + (splits[i+1] if i+1 < len(splits) else '')

            # 计算当前块中的引号数量
            quote_count += chunk.count('"') + \
                chunk.count('"') + chunk.count('"')
            quote_count += chunk.count('「') + chunk.count('」')
            quote_count += chunk.count('『') + chunk.count('』')

            # 如果在引号内或当前块太短，继续累积
            if quote_count % 2 == 1 or (len(current_chunk) + len(chunk) < min_length and i < len(splits)-2):
                current_chunk += chunk
            else:
                if current_chunk:
                    chunks.append(current_chunk + chunk)
                    current_chunk = ""
                else:
                    chunks.append(chunk)
                quote_count = 0  # 重置引号计数

    # 处理最后剩余的文本
    if splits[-1] or current_chunk:
        last_chunk = splits[-1] if splits[-1] else ""
        if current_chunk:
            chunks.append(current_chunk + last_chunk)
        elif last_chunk:
            chunks.append(last_chunk)

    # 清理并返回结果
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def convert_to_pinyin(text: str, style: str = 'tone_marks') -> str:
    """
    Convert Chinese text to pinyin with specified style
    style: 'tone_marks' (default) or 'tone_numbers'
    """
    try:
        # Select pinyin style based on parameter
        if style == 'tone_numbers':
            pinyin_style = pypinyin.TONE3
        else:  # default to tone marks
            pinyin_style = pypinyin.TONE

        # Convert to pinyin with selected style
        pinyin_list = pypinyin.pinyin(text, style=pinyin_style)
        # Flatten the list and join with spaces
        return ' '.join([item[0] for item in pinyin_list])
    except Exception as e:
        print(f"Error converting to pinyin: {e}")
        return "[Pinyin Error]"


def translate_text(text, target_lang):
    """Translate text using Azure Translator"""
    if 'translator' not in st.session_state:
        from translator import Translator
        st.session_state.translator = Translator()
    
    try:
        translation = st.session_state.translator.translate_text(text, target_lang)
        # print(f"Azure translated '{text}' to '{translation}'")  # Commented out for debugging
        return translation
    except Exception as e:
        print(f"Translation error: {str(e)}")
        return ""


def process_chunk(chunk: str, index: int, executor: ThreadPoolExecutor, include_english: bool, second_language: str, pinyin_style: str = 'tone_marks') -> tuple:
    try:
        # Get pinyin with specified style
        pinyin = convert_to_pinyin(chunk, pinyin_style)

        # Get translations using Azure
        translations = []
        if include_english:
            english = translate_text(chunk, 'en')
            if english:
                # print(f"English translation: {english}")  # Commented out for debugging
                translations.append(english or "[Translation Error]")

        second_trans = translate_text(chunk, second_language)
        if second_trans:
            # print(f"Second language translation: {second_trans}")  # Commented out for debugging
            translations.append(second_trans or "[Translation Error]")

        return (index, chunk, pinyin, *translations)

    except Exception as e:
        print(f"\nError processing chunk {index}: {e}")
        error_translations = ["[Translation Error]"] * (1 + int(include_english))
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


def process_text(file_path, include_english=True, second_language="vi", pinyin_style='tone_marks'):
    """Process text with language options and pinyin style"""
    print("\nCounting total chunks...")
    with open(file_path, 'r', encoding='utf-8') as file:
        total_chunks = sum(len(split_sentence(line.strip()))
                           for line in file if line.strip())

    print(f"Found {total_chunks} chunks to process")
    print("Note: Processing may slow down occasionally to avoid rate limits")

    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    with open('template.html', 'r', encoding='utf-8') as template_file:
        html_content = template_file.read()

    translation_content = ''
    global_index = 0

    max_workers = 3

    pbar = tqdm(
        total=total_chunks,
        desc="Translating",
        unit="chunk",
        ncols=100,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]"
    )

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
                pbar.update(1)
            except Exception as e:
                print(f"\nError getting result: {e}")
                continue

    pbar.close()

    all_results.sort(key=lambda x: (x[0], x[1]))

    current_line = -1
    for line_idx, chunk_idx, result in all_results:
        if line_idx != current_line:
            if current_line != -1:
                translation_content += '</div>'
            translation_content += '<div class="translation-block">'
            current_line = line_idx

        # Pass include_english to create_html_block
        translation_content += create_html_block(result, include_english)

    if all_results:
        translation_content += '</div>'

    html_content = html_content.replace('{{content}}', translation_content)
    return html_content


def process_interactive_chunk(chunk: str, index: int, executor: ThreadPoolExecutor, include_english: bool, second_language: str, pinyin_style: str = 'tone_marks') -> tuple:
    """Process chunk for interactive word-by-word translation"""
    try:
        # 使用 translator 处理文本
        if 'translator' not in st.session_state:
            from translator import Translator
            st.session_state.translator = Translator()
        
        # 直接使用 translator 的处理结果
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
    
    # 初始化HTML内容
    content_html = '<div class="interactive-text">'
    
    # 跟踪当前段落
    current_paragraph = []
    paragraphs = []
    
    # 按段落分组词语
    for word in word_data:
        if word.get('word') == '\n':
            if current_paragraph:
                paragraphs.append(current_paragraph)
                current_paragraph = []
        else:
            current_paragraph.append(word)
    
    if current_paragraph:
        paragraphs.append(current_paragraph)
    
    # 生成每个段落的HTML
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
            
            if progress_callback:
                progress_callback(0)
            
            # 先创建内容
            translation_content = create_interactive_html_block(
                (text, processed_words),
                include_english
            )
            
            if progress_callback:
                progress_callback(100)
                
            return html_content.replace('{{content}}', translation_content)
        else:
            # 保持标准翻译模式的代码完全不变
            chunks = split_sentence(text)
            total_chunks = len(chunks)
            chunks_processed = 0

            translation_content = ""
            
            if progress_callback:
                progress_callback(0)
                print(f"Total chunks: {total_chunks}")

            for chunk in chunks:
                result = process_chunk(
                    chunk, chunks_processed, None, 
                    include_english, second_language, pinyin_style
                )
                
                translation_content += create_html_block(result, include_english)
                
                chunks_processed += 1
                if progress_callback:
                    current_progress = min(100, (chunks_processed / total_chunks) * 100)
                    print(f"Processing chunk {chunks_processed}/{total_chunks} ({current_progress:.1f}%)")
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
    """Main entry point for command line usage"""
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
