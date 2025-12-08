import streamlit as st
import os
from io import BytesIO
from password_manager import PasswordManager
import pandas as pd
import streamlit.components.v1 as components
import json
from translator import Translator

# --- CẤU HÌNH TRANG ---
st.set_page_config(
    page_title="Multi-Language Translator", 
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Initialize password manager
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

# Hàm đếm ký tự
def count_characters(text):
    return len(text.replace(" ", "").replace("\n", ""))

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

    if user_password is None:
        user_password = st.text_input("Enter your access key", type="password")
        if not user_password:
            st.warning("Please enter your access key")
            return
        if not pm.check_password(user_password):
            st.error("Invalid access key")
            return

    # --- GIAO DIỆN CHÍNH ---
    st.header("🌍 Multi-Language Translator")
    
    st.subheader("Settings")
    
    # 1. CHỌN NGÔN NGỮ (SOURCE & TARGET)
    c1, c2 = st.columns(2)
    languages_list = ["Vietnamese", "English", "Chinese (Simplified)", "Japanese", "Korean", "French"]
    
    with c1:
        source_lang = st.selectbox("From (Nguồn):", languages_list, index=2) # Mặc định Chinese
    with c2:
        target_lang = st.selectbox("To (Đích):", languages_list, index=0) # Mặc định Vietnamese

    # 2. CHỌN CHẾ ĐỘ
    translation_mode = st.radio(
        "Mode:",
        ["Standard Translation (Dịch đoạn)", "Interactive Analysis (Phân tích từ)"],
        horizontal=True,
        help="Standard: Dịch mượt mà cả câu.\nInteractive: Tách từng từ để học (kèm phiên âm)."
    )
        
    # 3. INPUT TEXT
    input_method = st.radio("Input method:", ["Paste Text", "Upload File"], horizontal=True)
    text_input = ""

    if input_method == "Paste Text":
        text_input = st.text_area("Enter text here:", height=200)
    elif input_method == "Upload File":
        uploaded_file = st.file_uploader("Upload text file", type=['txt'])
        if uploaded_file:
            text_input = uploaded_file.getvalue().decode('utf-8')
            st.text_area("Preview:", value=text_input, height=150)

    # Initialize translator
    translator = init_translator()

    # --- NÚT BẤM DỊCH ---
    if st.button("🚀 Translate Now", type="primary"):
        if not text_input.strip():
            st.error("Please enter text first!")
            return

        # Kiểm tra Quota
        chars_count = count_characters(text_input)
        if not pm.check_usage_limit(st.session_state.current_user, chars_count):
            st.error("Usage limit exceeded.")
            return
        
        pm.track_usage(st.session_state.current_user, chars_count)
        
        # --- XỬ LÝ DỊCH ---
        try:
            # MODE 1: INTERACTIVE (HỌC TỪ)
            if translation_mode == "Interactive Analysis (Phân tích từ)":
                with st.spinner("AI đang phân tích từ vựng & phiên âm..."):
                    processed_words = translator.analyze_paragraph(text_input, source_lang, target_lang)
                    
                    if not processed_words:
                        st.error("Không nhận được kết quả từ AI.")
                    else:
                        # CSS Tùy biến: Nếu là tiếng Trung thì font to, tiếng Anh thì font thường
                        font_size = "24px" if "Chinese" in source_lang else "18px"
                        
                        html_output = f"""
                        <style>
                            .word-container {{ display: inline-block; margin: 5px; text-align: center; cursor: pointer; position: relative; }}
                            .word-orig {{ font-size: {font_size}; font-weight: bold; color: #2c3e50; }}
                            .pronounce {{ font-size: 13px; color: #e74c3c; margin-bottom: 2px; font-family: monospace; }}
                            .word-container:hover {{ background-color: #fff3cd; border-radius: 5px; }}
                            .word-container:hover::after {{
                                content: attr(title);
                                position: absolute;
                                bottom: 100%; left: 50%; transform: translateX(-50%);
                                background: #333; color: #fff; padding: 5px 10px;
                                border-radius: 5px; font-size: 14px; white-space: nowrap; z-index: 1000;
                            }}
                        </style>
                        <div style='line-height: 1.6; padding: 20px; background: white; border-radius: 10px; border: 1px solid #ddd;'>
                        """
                        
                        for item in processed_words:
                            w = item.get('word', '')
                            p = item.get('pinyin', '') # Có thể là Pinyin hoặc IPA
                            t = item.get('translation', '')
                            
                            html_output += f"""
                            <div class="word-container" title="{t}">
                                <div class="pronounce">{p}</div>
                                <div class="word-orig">{w}</div>
                            </div>
                            """
                        html_output += "</div>"
                        
                        st.success("✅ Phân tích xong! (Di chuột vào từ để xem nghĩa)")
                        components.html(html_output, height=600, scrolling=True)

            # MODE 2: STANDARD (DỊCH ĐOẠN)
            else:
                with st.spinner("Đang dịch..."):
                    result = translator.translate_standard(text_input, source_lang, target_lang)
                    st.success("✅ Kết quả:")
                    
                    # Chị cần dùng st.text_area để có thể copy/paste được
                    st.text_area("Kết quả:", value=result, height=300)
                    
                    # Nút 1: Tải về file .TXT (Văn bản thuần túy)
                    st.download_button("💾 Download Text (TXT)", result, file_name="translation.txt")
                    
                    # Nút 2: Tải về file .HTML (Giữ nguyên định dạng Markdown nếu có)
                    # Chuyển kết quả sang định dạng HTML
                    html_content = f"""
                    <!DOCTYPE html>
                    <html>
                    <head><meta charset="utf-8"><title>Translation Result</title></head>
                    <body>
                    <h1>Translation from {source_lang} to {target_lang}</h1>
                    <hr>
                    <pre style="white-space: pre-wrap; font-family: sans-serif; font-size: 16px;">{result}</pre>
                    </body>
                    </html>
                    """
                    st.download_button(
                        "🌐 Download HTML", 
                        html_content, 
                        file_name="translation_result.html", 
                        mime="text/html"
                    )

        except Exception as e:
            st.error(f"Lỗi: {str(e)}")

def show_admin_interface():
    st.title("Admin Dashboard")
    if not init_password_manager(): return
    try:
        stats = pm.get_usage_stats()
        st.write(stats)
    except: pass

def main():
    url_key = st.query_params.get('key', None)
    
    # Sidebar Login Admin
    with st.sidebar:
        st.title("Admin")
        admin_pass = st.text_input("Key", type="password")
        if st.button("Login Admin"):
            if init_password_manager() and pm.is_admin(admin_pass):
                st.session_state.user_logged_in = True
                st.session_state.current_user = admin_pass
                st.session_state.is_admin = True
                st.rerun()

    # User Login
    if not st.session_state.get('user_logged_in', False):
        if url_key and init_password_manager() and pm.check_password(url_key):
                st.session_state.user_logged_in = True
                st.session_state.current_user = url_key
                st.session_state.is_admin = False
                st.rerun()
        
        st.title("🌍 AI Translator")
        user_pass = st.text_input("Access Key", type="password")
        if st.button("Login"):
            if init_password_manager() and pm.check_password(user_pass):
                st.session_state.user_logged_in = True
                st.session_state.current_user = user_pass
                st.session_state.is_admin = False
                st.rerun()
            else: st.error("Invalid Key")
    else:
        if st.session_state.get('is_admin', False): show_admin_interface()
        else: show_user_interface(st.session_state.current_user)

if __name__ == "__main__":
    main()
