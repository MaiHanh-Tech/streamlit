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


# Khai báo Dictionary Languages ở phạm vi toàn cục
LANGUAGES = {
    "Arabic": "ar",
    "Chinese": "zh", # Đặt Tiếng Trung ở đây
    "English": "en",
    "French": "fr",
    "Indonesian": "id",
    "Italian": "it",
    "Japanese": "ja",
    "Korean": "ko",
    "Persian": "fa",
    "Portuguese": "pt",
    "Russian": "ru",
    "Spanish": "es",
    "Thai": "th",
    "Uzbek": "uz",
    "Vietnamese": "vi" # Đặt Tiếng Việt ở đây
}


# Initialize password manager only when needed
pm = None


def init_password_manager():
    global pm
    if pm is None:
        try:
            pm = PasswordManager()
            return True
        except Exception as e:
            st.error(f"Error initializing password manager: {str(e)}")
            return False
    return True


def init_translator():
    if 'translator' not in st.session_state:
        st.session_state.translator = Translator()
    return st.session_state.translator


def count_characters(text, include_english=True, target_language=None):
    """Count characters according to Azure Translator rules (kept for tracking)"""
    text = text.replace(" ", "").replace("\n", "")
    char_count = len(text)
    
    # Logic cũ: Nếu dịch sang ngôn ngữ khác ngoài Anh, và include English, thì tính gấp đôi.
    if include_english and target_language and target_language != "English":
        char_count *= 2
        
    return char_count


def update_progress(progress, progress_bar, status_text):
    """Update the progress bar and status text"""
    progress_bar.progress(progress/100)
    status_text.text(f"Processing... {progress:.1f}% completed")


def create_interactive_html(processed_words, pinyin_style):
    """Create HTML content for interactive translation (Đã chuyển lên đây)"""
    try:
        # Giả định template.html tồn tại
        with open('template.html', 'r', encoding='utf-8') as template_file:
            html_content = template_file.read()
        
        if processed_words is None:
            raise ValueError("processed_words cannot be None")
            
        # Import lại hàm tạo HTML từ translate_book (nếu cần)
        from translate_book import create_interactive_html_block
        
        # Create translation content
        translation_content = create_interactive_html_block(
            (None, [word for word in processed_words if word is not None]), 
            True 
        )
            
        if translation_content is None:
            raise ValueError("Failed to generate translation content")
            
        return html_content.replace('{{content}}', translation_content)
        
    except Exception as e:
        # st.error(f"Error creating interactive HTML: {str(e)}")
        return None


def show_user_interface(user_password=None):
    if not init_password_manager():
        return

    # Add logout button
    col1, col2 = st.columns([10, 1])
    with col2:
        if st.button("Logout"):
            st.session_state.user_logged_in = False
            st.session_state.current_user = None
            st.session_state.is_admin = False
            st.rerun()

    if user_password is None:
        user_password = st.text_input("Enter your access key", type="password")
        if not user_password:
            st.warning("Please enter your access key to use the translator")
            return

        if not pm.check_password(user_password):
            st.error("Invalid access key")
            return

    # Translation Settings
    st.header("Translation Settings")
    
    # Add translation mode selection
    st.subheader("Choose Translation Mode")
    translation_mode = st.radio(
        "",
        ["Standard Translation", "Interactive Word-by-Word"],
        help="Standard Translation: Full sentence translation with pinyin\nInteractive Word-by-Word: Click on individual words to see translations and hear pronunciation"
    )

    # --- KHỐI CHỌN NGÔN NGỮ NGUỒN VÀ ĐÍCH (ĐÃ SỬA) ---
    st.subheader("Select Languages")
    
    col_lang1, col_lang2, col_opt = st.columns([1, 1, 1])
    
    languages_list = list(LANGUAGES.keys())
    
    with col_lang1:
        # Nút chọn Ngôn ngữ Nguồn (Source)
        source_language = st.selectbox(
            "Source Language (Nguồn):",
            options=languages_list,
            index=languages_list.index("Chinese") if "Chinese" in languages_list else 0,
            placeholder="Choose source language..."
        )

    with col_lang2:
        # Nút chọn Ngôn ngữ Đích (Target)
        target_language = st.selectbox(
            "Target Language (Đích):",
            options=languages_list,
            index=languages_list.index("Vietnamese") if "Vietnamese" in languages_list else 0,
            placeholder="Choose target language..."
        )
        
    with col_opt:
        # Lấy lại include_english (Dùng cho logic tính quota và prompt AI)
        include_english = st.checkbox(
            "Include English Translation", 
            value=True,
            help="Include English translation alongside the target language"
        )

    # Kiểm tra nếu Source là Tiếng Anh và Include English thì cảnh báo
    if target_language == "English" and include_english:
        st.warning("English translation is already the target language.")
    
    # Pinyin Style (Chỉ áp dụng khi Source là Tiếng Trung)
    col_pinyin, _ = st.columns([1, 2])
    with col_pinyin:
        if source_language == "Chinese":
            pinyin_style = st.selectbox(
                'Pinyin Style',
                ['tone_marks', 'tone_numbers'],
                index=0,
                format_func=lambda x: 'Tone Marks (nǐ hǎo)' if x == 'tone_marks' else 'Tone Numbers (ni3 hao3)'
            )
        else:
            pinyin_style = 'none' # Mặc định là none nếu không phải tiếng Trung

    # Input Options
    input_method = st.radio("Choose input method:", [
                            "Paste Text", "Upload File", "Try Example"], key="input_method")

    text_input = ""

    if input_method == "Paste Text":
        text_container = st.container()
        with text_container:
            text_input = st.text_area(
                f"Paste {source_language} text here:",
                value="",
                height=500,
                key="simple_text_input",
                help="Paste your text here. The text will be split into sentences automatically."
            )

    elif input_method == "Upload File":
        uploaded_file = st.file_uploader(
            f"Upload {source_language} text file",
            type=['txt'],
            key="file_uploader",
            help="Upload a .txt file containing Chinese text"
        )
        if uploaded_file:
            try:
                text_input = uploaded_file.getvalue().decode('utf-8')
                text_input = st.text_area(
                    "Edit uploaded text if needed:",
                    value=text_input,
                    height=300,
                    key="uploaded_text_area"
                )
            except Exception as e:
                st.error(f"Error reading file: {str(e)}")

    else:  # Try Example
        # Cập nhật ví dụ nếu người dùng đổi ngôn ngữ nguồn
        if source_language == "Chinese":
            example_text = """第37届中国电影金鸡奖是2024年11月16日在中国厦门举行的中国电影颁奖礼，该届颁奖礼由中国文学艺术界联合会、中国电影家协会与厦门市人民政府共同主办。张艺执导的《第二十条》获最佳故事片奖。"""
        elif source_language == "English":
            example_text = "The quick brown fox jumps over the lazy dog. This is a crucial sentence for testing."
        else:
            example_text = f"Example text for {source_language}."
            
        text_input = st.text_area(
            "Example text (you can edit):",
            value=example_text,
            height=300,
            key="example_text_area"
        )

    # Initialize translator
    translator = init_translator()

    # Translation Button
    if st.button("Translate", key="translate_button"):
        if not target_language:
            st.error("Please select a target language!")
            return

        if not text_input.strip():
            st.error("Please enter or upload some text first!")
            return

        # Check usage limit
        chars_count = count_characters(text_input, include_english, target_language)
        if not pm.check_usage_limit(st.session_state.current_user, chars_count):
            daily_limit = pm.get_user_limit(st.session_state.current_user)
            st.error(f"You have exceeded your daily translation limit ({daily_limit:,} characters). Please try again tomorrow.")
            return
        
        # Track usage
        pm.track_usage(st.session_state.current_user, chars_count)
        
        # Show current usage
        daily_usage = pm.get_daily_usage(st.session_state.current_user)
        daily_limit = pm.get_user_limit(st.session_state.current_user)
        
        key_name = pm.get_key_name(st.session_state.current_user)
        user_tier = pm.user_tiers.get(key_name, "default")
        
        if user_tier == "premium" or pm.is_admin(st.session_state.current_user):
            st.markdown(
                f"""
                <div style="padding: 10px;">
                    Today's usage: {daily_usage:,}/{daily_limit:,} characters 
                    <span style="
                        background: linear-gradient(45deg, #FFD700, #FFA500);
                        -webkit-background-clip: text;
                        -webkit-text-fill-color: transparent;
                        font-weight: bold;
                        padding: 0 10px;
                        text-shadow: 0px 0px 10px rgba(255,215,0,0.3);
                        border: 1px solid #FFD700;
                        border-radius: 15px;
                        margin-left: 10px;
                    ">
                        Premium Account
                    </span>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            st.info(f"Today's usage: {daily_usage:,}/{daily_limit:,} characters")
        
        
        # --- START TRANSLATION LOGIC ---
        if translation_mode == "Interactive Word-by-Word":
            if source_language != "Chinese":
                 st.error("Interactive mode is currently only supported for Chinese source text.")
                 return

            try:
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Cắt văn bản thành từng câu/từng đoạn để xử lý song song
                paragraphs = text_input.split('\n')
                all_words = []
                
                # Step 1: Cắt từ và ghép lại
                status_text.text("Step 1/2: Segmenting text...")
                
                for paragraph in paragraphs:
                    if paragraph.strip(): 
                        words = [char for char in paragraph] 
                        all_words.extend(words)
                        all_words.append(' ') 
                    else:
                        all_words.append('\n')
                
                # Bước 2: Xử lý từng từ (Gọi Gemini)
                status_text.text("Step 2/2: Processing words in parallel...")
                
                processed_words = []
                total_chars = len([w for w in all_words if w.strip() and w != '\n'])
                word_count = 0
                
                for word in all_words:
                    if word.strip() and word != '\n':
                        result = translator.process_chinese_text(
                            word, 
                            LANGUAGES[target_language]
                        )
                        if result and len(result) > 0:
                            processed_words.append(result[0])
                        
                        word_count += 1
                        progress = 5 + (word_count / total_chars * 90)
                        progress_bar.progress(int(progress))
                    elif word == '\n':
                        processed_words.append({'word': '\n'})
                    
                # Bước 3: Generating HTML
                status_text.text("Generating interactive HTML...")
                progress_bar.progress(100)
                
                html_content = create_interactive_html(
                    processed_words,
                    pinyin_style
                )
                
                st.success("Translation completed!")
                st.download_button(
                    label="Download HTML",
                    data=html_content.encode('utf-8'),
                    file_name="translation.html",
                    mime="text/html; charset=utf-8"
                )
                components.html(html_content, height=800, scrolling=True)
                
            except Exception as e:
                st.error(f"Interactive Translation error: {str(e)}")

        else:
            # Standard translation mode
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Gọi hàm dịch cả đoạn
            html_content = translate_file(
                text_input,
                lambda p: update_progress(p, progress_bar, status_text),
                include_english,
                LANGUAGES[source_language], # Đã sửa
                LANGUAGES[target_language], # Đã sửa
                pinyin_style,
                translation_mode
            )
            
            # Cập nhật tiến trình
            progress_bar.progress(100)
            status_text.empty()
            
            st.success("Translation completed!")
            st.download_button(
                label="Download HTML",
                data=html_content.encode('utf-8'),
                file_name="translation.html",
                mime="text/html; charset=utf-8"
            )
            components.html(html_content, height=800, scrolling=True)
        
    except Exception as e:
        st.error(f"Translation error: {str(e)}")


def create_interactive_html(processed_words, pinyin_style):
    """Create HTML content for interactive translation (Đã chuyển lên đây)"""
    try:
        # Giả định template.html tồn tại
        with open('template.html', 'r', encoding='utf-8') as template_file:
            html_content = template_file.read()
        
        if processed_words is None:
            raise ValueError("processed_words cannot be None")
            
        # Import lại hàm tạo HTML từ translate_book
        from translate_book import create_interactive_html_block
        
        # Create translation content
        translation_content = create_interactive_html_block(
            (None, [word for word in processed_words if word is not None]), 
            True 
        )
            
        if translation_content is None:
            raise ValueError("Failed to generate translation content")
            
        return html_content.replace('{{content}}', translation_content)
        
    except Exception as e:
        # st.error(f"Error creating interactive HTML: {str(e)}")
        return None


def show_admin_interface(admin_password):
    """Show admin interface with usage statistics"""
    st.title("Admin Dashboard")
    
    if not init_password_manager():
        return
        
    try:
        stats = pm.get_usage_stats()
        
        st.header("Overall Statistics")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Users", stats['total_users'])
        with col2:
            total_chars = sum(sum(dates.values()) for dates in stats['user_stats'].values())
            st.metric("Total Characters Translated", f"{total_chars:,}")
        
        st.header("Daily Usage")
        daily_df = pd.DataFrame(
            list(stats['daily_stats'].items()),
            columns=['Date', 'Characters']
        )
        if not daily_df.empty:
            fig = go.Figure(data=[
                go.Bar(
                    x=daily_df['Date'],
                    y=daily_df['Characters'],
                    name='Daily Usage'
                )
            ])
            st.plotly_chart(fig)
        
    except Exception as e:
        st.error(f"Error loading statistics: {str(e)}")


def main():
    # Set page config again as a failsafe
    st.set_page_config(
        page_title="Translator App", 
        layout="centered",
        initial_sidebar_state="collapsed"
    )

    url_key = st.query_params.get('key', None)

    # Initialize translator
    if 'translator' not in st.session_state:
        st.session_state.translator = Translator()

    # Add admin login to sidebar
    with st.sidebar:
        st.title("Admin Access")
        admin_password = st.text_input("Enter admin key", type="password", key="admin_key")
        if st.button("Login as Admin"):
            if init_password_manager():
                if pm.is_admin(admin_password):
                    st.session_state.user_logged_in = True
                    st.session_state.current_user = admin_password
                    st.session_state.is_admin = True
                    st.rerun()
                else:
                    st.sidebar.error("Invalid admin key")

    # Check if user is already logged in
    if not st.session_state.get('user_logged_in', False):
        if url_key and init_password_manager():
            if pm.check_password(url_key):
                st.session_state.user_logged_in = True
                st.session_state.current_user = url_key
                st.session_state.is_admin = pm.is_admin(url_key)
                st.rerun()
            else:
                st.error("Invalid access key in URL")
                
        st.title("Chinese Text Translator")
        user_password = st.text_input("Enter your access key", type="password", key="user_key")
        if st.button("Login"):
            if init_password_manager():
                # CHỈ CẦN KIỂM TRA MẬT KHẨU CÓ HỢP LỆ HAY KHÔNG
                if pm.check_password(user_password):
                    st.session_state.user_logged_in = True
                    st.session_state.current_user = user_password
                    st.session_state.is_admin = pm.is_admin(user_password)
                    st.rerun()
                else:
                    st.error("Invalid access key")
    else:
        if st.session_state.get('is_admin', False):
            show_admin_interface(st.session_state.current_user)
        else:
            show_user_interface(st.session_state.current_user)


if __name__ == "__main__":
    main()
