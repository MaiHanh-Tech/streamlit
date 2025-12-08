import streamlit as st
import os
from translate_book import translate_file
from io import BytesIO
from password_manager import PasswordManager
import pandas as pd
import streamlit.components.v1 as components
from concurrent.futures import ThreadPoolExecutor, as_completed
import math
from translator import Translator
import plotly.graph_objects as go
import time
import json
import re

# Dictionary ngôn ngữ đích
LANGUAGES = {
    "Vietnamese": "vi",
    "English": "en",
    "French": "fr",
    "Japanese": "ja",
    "Korean": "ko",
    "Russian": "ru",
    "Spanish": "es",
    "Thai": "th"
}

# Initialize password manager
pm = None

def init_password_manager():
    global pm
    if pm is None:
        try:
            pm = PasswordManager()
            return True
        except: return False
    return True

def init_translator():
    if 'translator' not in st.session_state:
        st.session_state.translator = Translator()
    return st.session_state.translator

def count_characters(text, include_english=True, target_language=None):
    text = text.replace(" ", "").replace("\n", "")
    char_count = len(text)
    if include_english and target_language and target_language != "English":
        char_count *= 2
    return char_count

def update_progress(progress, progress_bar, status_text):
    progress_bar.progress(progress/100)
    status_text.text(f"Processing... {progress:.1f}% completed")

# Hàm tạo HTML cho Interactive Mode
def create_interactive_html(processed_words, pinyin_style):
    try:
        with open('template.html', 'r', encoding='utf-8') as template_file:
            html_content = template_file.read()
        
        if processed_words is None: return None
            
        from translate_book import create_interactive_html_block
        translation_content = create_interactive_html_block(
            (None, [word for word in processed_words if word is not None]), 
            True 
        )
        return html_content.replace('{{content}}', translation_content)
    except: return None

def show_user_interface(user_password=None):
    if not init_password_manager(): return

    # Logout
    col1, col2 = st.columns([10, 1])
    with col2:
        if st.button("Logout"):
            st.session_state.user_logged_in = False
            st.session_state.current_user = None
            st.session_state.is_admin = False
            st.rerun()

    # Login check
    if user_password is None:
        user_password = st.text_input("Enter your access key", type="password")
        if not user_password: return
        if not pm.check_password(user_password):
            st.error("Invalid access key")
            return

    # --- GIAO DIỆN CHÍNH (QUAY VỀ BẢN DỊCH TRUNG) ---
    st.header("Chinese Translation Settings")
    
    translation_mode = st.radio(
        "Mode:",
        ["Standard Translation", "Interactive Word-by-Word"],
        help="Standard: Dịch cả câu.\nInteractive: Học từ vựng."
    )

    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        include_english = st.checkbox("Include English Translation", value=True)

    with col2:
        target_language = st.selectbox(
            "Select Target Language:",
            options=list(LANGUAGES.keys()),
            index=0 # Vietnamese
        )

    with col3:
        pinyin_style = st.selectbox('Pinyin Style', ['tone_marks', 'tone_numbers'])
        
    if target_language == "English" and include_english:
        st.warning("English is already selected.")

    # Input
    input_method = st.radio("Input method:", ["Paste Text", "Upload File", "Try Example"])
    text_input = ""

    if input_method == "Paste Text":
        text_input = st.text_area("Paste Chinese text here:", height=300)
    elif input_method == "Upload File":
        uploaded_file = st.file_uploader("Upload .txt file", type=['txt'])
        if uploaded_file:
            text_input = uploaded_file.getvalue().decode('utf-8')
            st.text_area("Preview:", value=text_input, height=150)
    else:
        text_input = """第37届中国电影金鸡奖是2024年11月16日在中国厦门举行的中国电影颁奖礼。"""
        st.text_area("Example:", value=text_input, height=100)

    translator = init_translator()

    # Translate Button
    if st.button("Translate", key="translate_button"):
        if not text_input.strip():
            st.error("Please enter text!")
            return

        # Quota check
        chars_count = count_characters(text_input, include_english, target_language)
        if not pm.check_usage_limit(st.session_state.current_user, chars_count):
            st.error("Daily limit exceeded.")
            return
        
        pm.track_usage(st.session_state.current_user, chars_count)
        
        try:
            # 1. INTERACTIVE MODE
            if translation_mode == "Interactive Word-by-Word":
                with st.spinner("Analyzing words..."):
                    paragraphs = text_input.split('\n')
                    all_words = []
                    for p in paragraphs:
                        if p.strip():
                            all_words.extend([c for c in p])
                            all_words.append(' ')
                        else: all_words.append('\n')
                    
                    processed_words = []
                    progress_bar = st.progress(0)
                    total = len(all_words)
                    
                    for i, word in enumerate(all_words):
                        if word.strip():
                            res = translator.process_chinese_text(word, LANGUAGES[target_language])
                            if res: processed_words.append(res[0])
                        elif word == '\n':
                            processed_words.append({'word': '\n'})
                        progress_bar.progress((i+1)/total)
                    
                    html_content = create_interactive_html(processed_words, pinyin_style)
                    st.success("Done!")
                    components.html(html_content, height=800, scrolling=True)

            # 2. STANDARD MODE
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                html_content = translate_file(
                    text_input,
                    lambda p: update_progress(p, progress_bar, status_text),
                    include_english,
                    LANGUAGES[target_language],
                    pinyin_style,
                    translation_mode
                )
                
                progress_bar.progress(100)
                status_text.empty()
                st.success("Done!")
                
                st.download_button("Download HTML", html_content, "translation.html", "text/html")
                components.html(html_content, height=800, scrolling=True)
                
        except Exception as e:
            st.error(f"Error: {str(e)}")

def show_admin_interface(user):
    st.title("Admin")
    if not init_password_manager(): return
    try:
        stats = pm.get_usage_stats()
        st.write(stats)
    except: pass

def main():
    st.set_page_config(page_title="Chinese Translator", layout="centered")
    url_key = st.query_params.get('key', None)

    if 'translator' not in st.session_state:
        st.session_state.translator = Translator()

    # Sidebar Admin
    with st.sidebar:
        st.title("Admin")
        admin_pass = st.text_input("Key", type="password")
        if st.button("Login Admin"):
            if init_password_manager() and pm.is_admin(admin_pass):
                st.session_state.user_logged_in = True
                st.session_state.current_user = admin_pass
                st.session_state.is_admin = True
                st.rerun()

    # Logic Login đã fix
    if not st.session_state.get('user_logged_in', False):
        if url_key and init_password_manager():
            if pm.check_password(url_key):
                st.session_state.user_logged_in = True
                st.session_state.current_user = url_key
                st.session_state.is_admin = pm.is_admin(url_key)
                st.rerun()
                
        st.title("Chinese Text Translator")
        user_pass = st.text_input("Access Key", type="password", key="u_pass")
        if st.button("Login"):
            if init_password_manager() and pm.check_password(user_pass):
                st.session_state.user_logged_in = True
                st.session_state.current_user = user_pass
                st.session_state.is_admin = pm.is_admin(user_pass)
                st.rerun()
            else: st.error("Invalid key")
    else:
        if st.session_state.get('is_admin', False):
            show_admin_interface(st.session_state.current_user)
        else:
            show_user_interface(st.session_state.current_user)

if __name__ == "__main__":
    main()
