import google.generativeai as genai
import streamlit as st
import json
import re
import time
from google.api_core.exceptions import ResourceExhausted
from pypinyin import pinyin, Style 

class Translator:
    def __init__(self):
        try:
            api_key = st.secrets["api_keys"]["gemini_api_key"]
            genai.configure(api_key=api_key)
            try: self.model = genai.GenerativeModel('gemini-1.5-flash')
            except: self.model = genai.GenerativeModel('gemini-pro')
        except: self.model = None
        self.translated_words = {} 

    def _run_gemini(self, prompt):
        if not self.model: return None
        for i in range(3):
            try:
                # Ép trả về JSON
                response = self.model.generate_content(prompt + "\nRETURN JSON ONLY.")
                text = response.text.strip()
                if "```" in text: text = re.sub(r'```json|```', '', text).strip()
                return json.loads(text)
            except: time.sleep(2)
        return None

    # HÀM NÀY ĐÃ ĐƯỢC SỬA VỀ CHUẨN 3 THAM SỐ
    def translate_text(self, text, target_lang, include_english):
        """Dịch đoạn văn Tiếng Trung"""
        cache_key = f"{text}_{target_lang}_{include_english}"
        if cache_key in self.translated_words: return self.translated_words[cache_key]
        
        target_name = st.session_state.languages.get(target_lang, target_lang) if 'languages' in st.session_state else target_lang
        
        # Prompt chuyên dụng cho Tiếng Trung
        prompt = f"""
        Translate this Chinese text to {target_name}.
        Input: "{text}"
        """
        
        if include_english and target_lang != 'en':
            prompt += f"""
            Output JSON format: 
            {{ 
                "target": "Translation in {target_name}", 
                "english": "Translation in English" 
            }}
            """
        else:
            prompt += f"""
            Output JSON format: {{ "target": "Translation in {target_name}" }}
            """
            
        data = self._run_gemini(prompt)
        
        if data:
            if include_english and target_lang != 'en':
                res = f"{data.get('target', '')}\n{data.get('english', '')}"
            else:
                res = data.get('target', '')
            
            self.translated_words[cache_key] = res
            return res
            
        return "[Error translating]"

    def process_chinese_text(self, word, target_lang):
        """Phân tích từ vựng (Interactive)"""
        pinyin_text = ""
        try:
            pinyin_list = pinyin(word, style=Style.TONE)[0][0]
            pinyin_text = ' '.join(pinyin_list)
        except: pass
        
        target_name = st.session_state.languages.get(target_lang, target_lang) if 'languages' in st.session_state else target_lang
        
        prompt = f"""
        Analyze Chinese word: "{word}". Target: {target_name}.
        Output JSON: [{{ "word": "{word}", "translations": ["Meaning 1", "Meaning 2"] }}]
        """
        
        data = self._run_gemini(prompt)
        if data and isinstance(data, list):
            result = {
                'word': word,
                'pinyin': pinyin_text,
                'translations': data[0].get('translations', [])
            }
            return [result]
            
        return [{'word': word, 'pinyin': pinyin_text, 'translations': ['...']}]
```

### 2. FILE `translate_book.py` (Bản Gốc - Gọi đúng 3 tham số)

```python
import pypinyin
import re
from concurrent.futures import ThreadPoolExecutor
import time
import random
import streamlit as st

def split_sentence(text):
    text = re.sub(r'\s+', ' ', text.strip())
    pattern = r'([。！？，：；.!?,][」"』\'）)]*(?:\s*[「""『\'（(]*)?)'
    splits = re.split(pattern, text)
    chunks = []
    current = ""
    for s in splits:
        if not s: continue
        if len(current) + len(s) < 20: current += s
        else:
            chunks.append(current)
            current = s
    if current: chunks.append(current)
    return [c.strip() for c in chunks if c.strip()]

def convert_to_pinyin(text, style='tone_marks'):
    try:
        p_style = pypinyin.TONE3 if style == 'tone_numbers' else pypinyin.TONE
        return ' '.join([i[0] for i in pypinyin.pinyin(text, style=p_style)])
    except: return ""

def translate_text(text, target, include_eng):
    if 'translator' not in st.session_state:
        from translator import Translator
        st.session_state.translator = Translator()
    # GỌI ĐÚNG 3 THAM SỐ KHỚP VỚI FILE TRANSLATOR
    return st.session_state.translator.translate_text(text, target, include_eng)

def process_chunk(chunk, index, executor, include_english, target_code, pinyin_style):
    time.sleep(0.2)
    try:
        # Luôn lấy Pinyin (vì App này chuyên Trung)
        pinyin_text = convert_to_pinyin(chunk, pinyin_style)
        
        # Dịch
        trans_res = translate_text(chunk, target_code, include_english)
        
        # Xử lý kết quả trả về từ Gemini
        parts = trans_res.split('\n')
        parts = [p for p in parts if p.strip()]
        
        if include_english and target_code != 'en':
            # Mong đợi: Dòng 1 đích, Dòng 2 anh
            target_val = parts[0] if len(parts) > 0 else "..."
            eng_val = parts[1] if len(parts) > 1 else "..."
            return (index, chunk, pinyin_text, eng_val, target_val)
        else:
            # Chỉ 1 dòng
            target_val = parts[0] if len(parts) > 0 else "..."
            return (index, chunk, pinyin_text, target_val)
            
    except Exception as e:
        err = f"[Err: {str(e)}]"
        if include_english: return (index, chunk, "", err, err)
        else: return (index, chunk, "", err)

def create_html_block(results, include_english):
    speak_btn = '''<button class="speak-button" onclick="speakSentence(this.parentElement.textContent.replace('🔊', ''))"><svg viewBox="0 0 24 24"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg></button>'''
    
    if include_english:
        idx, orig, pin, eng, sec = results
        return f'''<div class="sentence-part responsive"><div class="original">{idx+1}. {orig}{speak_btn}</div><div class="pinyin">{pin}</div><div class="english">{eng}</div><div class="second-language">{sec}</div></div>'''
    else:
        idx, orig, pin, sec = results
        return f'''<div class="sentence-part responsive"><div class="original">{idx+1}. {orig}{speak_btn}</div><div class="pinyin">{pin}</div><div class="second-language">{sec}</div></div>'''

def create_interactive_html_block(results, include_english):
    chunk, word_data = results
    html = '<div class="interactive-text">'
    html += '<p class="interactive-paragraph">'
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
        if progress_callback: progress_callback(100)
        content = create_interactive_html_block((input_text, processed_words), include_english)
        return template.replace('{{content}}', content)
        
    chunks = split_sentence(input_text)
    total = len(chunks)
    html = ""
    
    with ThreadPoolExecutor(max_workers=3) as ex:
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
