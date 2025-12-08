import streamlit as st
import os
from io import BytesIO
from password_manager import PasswordManager
import pandas as pd
# from reportlab.pdfgen import canvas # Không dùng nữa (giữ nguyên gốc)
# from reportlab.lib.pagesizes import A4
# from reportlab.pdfbase import pdfmetrics
# from reportlab.pdfbase.ttfonts import TTFont
import streamlit.components.v1 as components
# import jieba # Bỏ vì lỗi
from concurrent.futures import ThreadPoolExecutor, as_completed
import math
from translator import Translator
import plotly.graph_objects as go
import json 
import time
import re

# Khai báo Dictionary Languages ở phạm vi toàn cục để Translator.py dùng được
LANGUAGES = {
    "Arabic": "ar",
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
    "Vietnamese": "vi"
}
st.session_state.languages = LANGUAGES # Lưu vào session để Translator.py lấy


# Initialize password manager only when needed
pm = None


def init_password_manager():
    global pm
    if pm is None:
        try:
            # GIẢ ĐỊNH file password_manager.py TỒN TẠI
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


def count_characters(text, include_english=True, second_language=None):
    """Count characters according to Azure Translator rules"""
    text = text.replace(" ", "").replace("\n", "")
    char_count = len(text)
    
    if include_english and second_language and second_language != "English":
        char_count *= 2
        
    return char_count


def update_progress(progress, progress_bar, status_text):
    """Update the progress bar and status text"""
    progress_bar.progress(progress/100)
    status_text.text(f"Processing... {progress:.1f}% completed")


# Hàm tạo HTML cho Interactive (Làm lại logic)
def create_interactive_html(processed_words, pinyin_style):
    """Create HTML with hover tooltips for each word"""
    html_output = """
    <style>
        .word-container { display: inline-block; margin: 5px; text-align: center; cursor: pointer; position: relative; }
        .zh-word { font-size: 24px; font-weight: bold; color: #2c3e50; }
        .pinyin { font-size: 14px; color: #7f8c8d; margin-bottom: 2px; }
        .word-container:hover { background-color: #e8f0fe; border-radius: 5px; }
        .word-container:hover::after {
            content: attr(title);
            position: absolute;
            bottom: 100%;
            left: 50%;
            transform: translateX(-50%);
            background: #333;
            color: #fff;
            padding: 5px 10px;
            border-radius: 5px;
            font-size: 14px;
            white-space: nowrap;
            z-index: 1000;
            pointer-events: none;
        }
    </style>
    <div style='line-height: 1.6; padding: 20px; background: white; border-radius: 10px; border: 1px solid #ddd;'>
    """
    
    # Xử lý Pinyin Style
    def format_pinyin(pinyin, style):
        if style == 'tone_numbers':
            # Logic phức tạp để chuyển tone marks sang numbers (Ví dụ: nǐ hǎo -> ni3 hao3)
            return pinyin.replace('ā', 'a1').replace('á', 'a2').replace('ǎ', 'a3').replace('à', 'a4').replace('ō', 'o1').replace('ó', 'o2').replace('ǒ', 'o3').replace('ò', 'o4').replace('ē', 'e1').replace('é', 'e2').replace('ě', 'e3').replace('è', 'e4').replace('ī', 'i1').replace('í', 'i2').replace('ǐ', 'i3').replace('ì', 'i4').replace('ū', 'u1').replace('ú', 'u2').replace('ǔ', 'u3').replace('ù', 'u4').replace('ü', 'v').replace('ǖ', 'v1').replace('ǘ', 'v2').replace('ǚ', 'v3').replace('ǜ', 'v4')
        return pinyin # Giữ nguyên tone marks
    
    try:
        for item in processed_words:
            w = item.get('word', '')
            p = item.get('pinyin', '')
            t = ", ".join(item.get('translations', ['...']))
            
            p_formatted = format_pinyin(p, pinyin_style)
            
            html_output += f"""
            <div class="word-container" title="{t}">
                <div class="pinyin">{p_formatted}</div>
                <div class="zh-word">{w}</div>
            </div>
            """
    except Exception as e:
        html_output += f"Lỗi tạo HTML: {str(e)}"
        
    html_output += "</div>"
    return html_output

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

    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        include_english = st.checkbox(
            "Include English Translation", 
            value=True,
            help="Include English translation alongside the second language"
        )

    with col2:
        second_language = st.selectbox(
            "Select Second Language (Required)",
            options=list(LANGUAGES.keys()),
            index=None,
            placeholder="Choose a language..."
        )

    with col3:
        pinyin_style = st.selectbox(
            'Pinyin Style',
            ['tone_marks', 'tone_numbers'],
            index=0,
            format_func=lambda x: 'Tone Marks (nǐ hǎo)' if x == 'tone_marks' else 'Tone Numbers (ni3 hao3)'
        )
        
    if second_language == "English" and include_english:
        st.warning("English translation is already enabled via checkbox")
        second_language = None

    # Input Options
    input_method = st.radio("Choose input method:", [
                            "Paste Text", "Upload File", "Try Example"], key="input_method")

    text_input = ""

    if input_method == "Paste Text":
        text_container = st.container()
        with text_container:
            text_input = st.text_area(
                "Paste Chinese text here",
                value="",
                height=500,
                key="simple_text_input",
                help="Paste your Chinese text here. The text will be split into sentences automatically."
            )

    elif input_method == "Upload File":
        uploaded_file = st.file_uploader(
            "Upload Chinese text file",
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
        example_text = """第37届中国电影金鸡奖是2024年11月16日在中国厦门举行的中国电影颁奖礼，该届颁奖礼由中国文学艺术界联合会、中国电影家协会与厦门市人民政府共同主办。张艺执导的《第二十条》获最佳故事片奖。"""
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
        if not second_language:
            st.error("Please select a second language before translating!")
            return

        if not text_input.strip():
            st.error("Please enter or upload some text first!")
            return

        try:
            # Check usage limit
            chars_count = count_characters(text_input, include_english, second_language)
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
                try:
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    # Cắt văn bản thành từng câu/từng đoạn để xử lý song song (Giống logic cũ)
                    paragraphs = text_input.split('\n')
                    all_words = []
                    
                    # Bước 1: Cắt từ và ghép lại
                    for paragraph in paragraphs:
                        if paragraph.strip(): 
                            # Giả lập lại logic cắt từ của jieba (chỉ lấy words)
                            words = [char for char in paragraph] # Cắt theo ký tự
                            all_words.extend(words)
                            all_words.append(' ') # Thêm khoảng trắng
                        else:
                            all_words.append('\n')
                    
                    # Xử lý song song (Do Gemini cực nhanh nên không cần ThreadPool, nhưng em giữ lại cấu trúc cũ cho chị)
                    processed_words = []
                    total_words = len([w for w in all_words if w.strip()])
                    word_count = 0
                    
                    for word in all_words:
                        if word.strip() and word != '\n':
                            # Gọi hàm xử lý của Translator.py (Gemini)
                            result = translator.process_chinese_text(
                                word, 
                                LANGUAGES[second_language]
                            )
                            if result and len(result) > 0:
                                processed_words.append(result[0])
                            
                            word_count += 1
                            progress = 5 + (word_count / total_words * 90)
                            progress_bar.progress(int(progress))
                        elif word == '\n':
                            processed_words.append({'word': '\n'})
                        
                        
                    # Bước 2: Generating HTML
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
                
                # Hàm dịch cả đoạn (có cập nhật tiến trình giả lập)
                progress_bar.progress(10)
                status_text.text("Dịch cả đoạn (1/1)...")
                
                html_content = translator.translate_text(
                    text_input,
                    LANGUAGES[second_language],
                    include_english
                )
                
                progress_bar.progress(100)
                status_text.empty()
                
                st.success("Translation completed!")
                st.download_button(
                    label="Download Translation",
                    data=html_content.encode('utf-8'),
                    file_name="translation.txt",
                    mime="text/plain"
                )
                st.text_area("Result:", html_content, height=500)
            
        except Exception as e:
            st.error(f"Translation error: {str(e)}")


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
        # Try to login with URL key if present
        if url_key and init_password_manager():
            if pm.check_password(url_key):
                st.session_state.user_logged_in = True
                st.session_state.current_user = url_key
                # Admin/MaiHanhPremium không được set is_admin ở đây, mà set sau khi check_password
                st.session_state.is_admin = pm.is_admin(url_key) 
                st.rerun()
            else:
                st.error("Invalid access key in URL")
                
        # Show regular login form if no URL key or invalid URL key
        st.title("Chinese Text Translator")
        user_password = st.text_input("Enter your access key", type="password", key="user_key")
        if st.button("Login"):
            if init_password_manager():
                # CHỈ CẦN KIỂM TRA MẬT KHẨU CÓ HỢP LỆ HAY KHÔNG
                if pm.check_password(user_password):
                    st.session_state.user_logged_in = True
                    st.session_state.current_user = user_password
                    # Dùng is_admin để xác định có vào Admin Dashboard không
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
