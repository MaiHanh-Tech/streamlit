import streamlit as st
import os
from io import BytesIO
from password_manager import PasswordManager
import pandas as pd
import streamlit.components.v1 as components
import jieba
import json
from translator import Translator

# --- CẤU HÌNH TRANG ---
st.set_page_config(
    page_title="Translator App", 
    layout="centered",
    initial_sidebar_state="collapsed"
)

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

# Hàm đếm ký tự để trừ tiền/quota
def count_characters(text, include_english=True, second_language=None):
    text = text.replace(" ", "").replace("\n", "")
    char_count = len(text)
    if include_english and second_language and second_language != "English":
        char_count *= 2
    return char_count

# Hàm cập nhật thanh tiến trình (Giữ lại để tương thích, dù Gemini chạy rất nhanh)
def update_progress(progress, progress_bar, status_text):
    progress_bar.progress(progress/100)
    status_text.text(f"Processing... {progress:.1f}% completed")

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

    # --- GIAO DIỆN CHÍNH ---
    st.header("Translation Settings")
    
    st.subheader("Choose Translation Mode")
    translation_mode = st.radio(
        "",
        ["Standard Translation", "Interactive Word-by-Word"],
        help="Standard: Dịch cả câu/đoạn.\nInteractive: Phân tích từng từ, Pinyin và nghĩa."
    )

    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        include_english = st.checkbox("Include English Translation", value=True)

    with col2:
        languages = {
            "Vietnamese": "vi",
            "English": "en",
            "French": "fr",
            "Japanese": "ja",
            "Korean": "ko"
        }
        second_language = st.selectbox(
            "Select Second Language (Required)",
            options=list(languages.keys()),
            index=0 # Mặc định là Tiếng Việt cho tiện
        )

    with col3:
        pinyin_style = st.selectbox('Pinyin Style', ['tone_marks', 'tone_numbers'])
        
    # Input Options
    input_method = st.radio("Choose input method:", ["Paste Text", "Upload File", "Try Example"])
    text_input = ""

    if input_method == "Paste Text":
        text_input = st.text_area("Paste Chinese text here", height=300)
    elif input_method == "Upload File":
        uploaded_file = st.file_uploader("Upload Chinese text file", type=['txt'])
        if uploaded_file:
            text_input = uploaded_file.getvalue().decode('utf-8')
            st.text_area("Preview:", value=text_input, height=150)
    else:
        text_input = "第37届中国电影金鸡奖是2024年11月16日在中国厦门举行的..."
        st.text_area("Example:", value=text_input, height=100)

    # Initialize translator
    translator = init_translator()

    # --- NÚT BẤM DỊCH (LOGIC MỚI - ĐÃ SỬA LỖI) ---
    if st.button("Translate", key="translate_button"):
        if not second_language:
            st.error("Please select a second language!")
            return
        if not text_input.strip():
            st.error("Please enter text first!")
            return

        try:
            # 1. Kiểm tra Quota (Giữ nguyên logic quản lý)
            chars_count = count_characters(text_input, include_english, second_language)
            if not pm.check_usage_limit(st.session_state.current_user, chars_count):
                st.error("Limit exceeded.")
                return
            
            pm.track_usage(st.session_state.current_user, chars_count)
            
            # Hiển thị thông tin sử dụng
            daily_usage = pm.get_daily_usage(st.session_state.current_user)
            limit = pm.get_user_limit(st.session_state.current_user)
            st.info(f"Usage today: {daily_usage}/{limit} chars")

            # 2. XỬ LÝ DỊCH THUẬT (DÙNG GEMINI)
            
            # --- CHẾ ĐỘ 1: INTERACTIVE WORD-BY-WORD ---
            if translation_mode == "Interactive Word-by-Word":
                try:
                    with st.spinner("AI đang phân tích sâu (Cắt từ + Pinyin + Nghĩa)..."):
                        # Gọi hàm mới trong translator.py
                        target_lang_name = list(languages.keys())[list(languages.values()).index(languages[second_language])]
                        
                        # Gọi Gemini xử lý cả đoạn
                        processed_words = translator.analyze_paragraph(text_input, target_lang_name)
                        
                        if not processed_words:
                            st.error("AI không trả về kết quả. Kiểm tra API Key.")
                        else:
                            # Tự tạo HTML tại đây (Không phụ thuộc file ngoài)
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
                            
                            for item in processed_words:
                                w = item.get('word', '')
                                p = item.get('pinyin', '')
                                t = item.get('translation', '')
                                html_output += f"""
                                <div class="word-container" title="{t}">
                                    <div class="pinyin">{p}</div>
                                    <div class="zh-word">{w}</div>
                                </div>
                                """
                            html_output += "</div>"
                            
                            st.success("✅ Phân tích hoàn tất!")
                            components.html(html_output, height=600, scrolling=True)
                            
                except Exception as e:
                    st.error(f"Lỗi Interactive Mode: {str(e)}")

            # --- CHẾ ĐỘ 2: STANDARD TRANSLATION ---
            else:
                try:
                    with st.spinner("AI đang dịch cả đoạn..."):
                        target_lang_name = list(languages.keys())[list(languages.values()).index(languages[second_language])]
                        
                        # Gọi hàm dịch cả đoạn (Cần đảm bảo translator.py có hàm này)
                        # Nếu translator.py chưa có, chị dùng tạm code gọi trực tiếp ở đây:
                        prompt = f"Translate this Chinese text to {target_lang_name}:\n{text_input}"
                        response = translator.model.generate_content(prompt)
                        result_text = response.text
                        
                        st.success("✅ Dịch hoàn tất!")
                        st.text_area("Kết quả:", value=result_text, height=300)
                        
                        # Nút tải về
                        st.download_button("💾 Tải kết quả", result_text, file_name="translation.txt")
                        
                except Exception as e:
                    st.error(f"Lỗi Standard Mode: {str(e)}")

        except Exception as e:
            st.error(f"Hệ thống gặp lỗi: {str(e)}")

def show_admin_interface():
    st.title("Admin Dashboard")
    if not init_password_manager(): return
    try:
        stats = pm.get_usage_stats()
        st.metric("Total Users", stats['total_users'])
        st.write("Daily Stats:", stats['daily_stats'])
    except Exception as e:
        st.error(f"Admin Error: {e}")

def main():
    # Lấy key từ URL (nếu có)
    url_key = st.query_params.get('key', None)

    # Khởi tạo Translator
    if 'translator' not in st.session_state:
        from translator import Translator
        st.session_state.translator = Translator()

    # Sidebar Login
    with st.sidebar:
        st.title("Admin Access")
        admin_pass = st.text_input("Admin Key", type="password")
        if st.button("Login Admin"):
            if init_password_manager() and pm.is_admin(admin_pass):
                st.session_state.user_logged_in = True
                st.session_state.current_user = admin_pass
                st.session_state.is_admin = True
                st.rerun()

    # Main Login Logic
    if not st.session_state.get('user_logged_in', False):
        if url_key and init_password_manager():
            if pm.check_password(url_key):
                st.session_state.user_logged_in = True
                st.session_state.current_user = url_key
                st.session_state.is_admin = False
                st.rerun()
        
        st.title("Chinese Text Translator (Gemini Powered)")
        user_pass = st.text_input("Access Key", type="password")
        if st.button("Login"):
            if init_password_manager() and pm.check_password(user_pass):
                st.session_state.user_logged_in = True
                st.session_state.current_user = user_pass
                st.session_state.is_admin = False
                st.rerun()
            else:
                st.error("Invalid Key")
    else:
        if st.session_state.get('is_admin', False):
            show_admin_interface()
        else:
            show_user_interface(st.session_state.current_user)

if __name__ == "__main__":
    main()
