import streamlit as st
import os
from translate_book import translate_file, create_interactive_html_block
from io import BytesIO
from password_manager import PasswordManager
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import streamlit.components.v1 as components
import jieba
from concurrent.futures import ThreadPoolExecutor, as_completed
import math
from translator import Translator
import plotly.graph_objects as go


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
        print("Translator initialized in session state")
    return st.session_state.translator


def show_user_interface(user_password=None):
    if not init_password_manager():
        return

    # Add logout button in top right corner
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
        languages = {
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

        second_language = st.selectbox(
            "Select Second Language (Required)",
            options=list(languages.keys()),
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

    # Initialize text_input outside the if blocks
    text_input = ""

    if input_method == "Paste Text":
        # Create a container for text input
        text_container = st.container()
        with text_container:
            # Simple text area with reduced height from 800 to 500
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
                # Show the uploaded text in a text area that can be edited
                text_input = st.text_area(
                    "Edit uploaded text if needed:",
                    value=text_input,
                    height=300,
                    key="uploaded_text_area"
                )
            except Exception as e:
                st.error(f"Error reading file: {str(e)}")

    else:  # Try Example
        example_text = """第37届中国电影金鸡奖是2024年11月16日在中国厦门举的中国电影颁奖礼[2]，该届颁奖礼由中国文学艺术界联合会、中国电影家协会与厦门市人民政府共同主办。2024年10月27日公布评委会名名单[3][4]，颁奖典礼主持人由电影频道主持人蓝羽与演员佟大为担任[5]。

张艺执导的《第二十条》获最佳故事片奖，陈凯歌凭借《志愿军：雄兵出击》获得最佳导演，音、李庚希分别凭借《第二十条》和《我们一起太阳》获得最佳男主角奖[6]，李庚希亦成为中电影金鸡奖的第一位"00后"影后[7]。
"""
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
            # Check usage limit before translation using Azure counting rules
            chars_count = count_characters(text_input, include_english, second_language)
            if not pm.check_usage_limit(st.session_state.current_user, chars_count):
                daily_limit = pm.get_user_limit(st.session_state.current_user)
                st.error(f"You have exceeded your daily translation limit ({daily_limit:,} characters). Please try again tomorrow.")
                return
            
            # Track usage if translation succeeds
            pm.track_usage(st.session_state.current_user, chars_count)
            
            # Show current usage with premium status
            daily_usage = pm.get_daily_usage(st.session_state.current_user)
            daily_limit = pm.get_user_limit(st.session_state.current_user)
            
            # Get user's tier
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
            
            if translation_mode == "Interactive Word-by-Word":
                try:
                    with st.spinner("AI đang phân tích sâu (Cắt từ + Pinyin + Nghĩa)..."):
                        
                        # CÁCH MỚI: GỬI TRỌN GÓI CHO GEMINI (SIÊU TỐC ĐỘ)
                        # Thay vì cắt từ bằng jieba rồi dịch từng cái (Rất lâu & tốn Request)
                        # Chúng ta nhờ Gemini làm tất cả trong 1 lần gọi.
                        
                        target_lang_name = list(languages.keys())[list(languages.values()).index(languages[second_language])]
                        
                        prompt_analysis = f"""
                        Phân tích đoạn văn tiếng Trung sau đây để học tập.
                        Đoạn văn: "{text_input}"
                        Ngôn ngữ đích: {target_lang_name}
                        
                        Yêu cầu:
                        1. Cắt đoạn văn thành các từ/cụm từ có nghĩa (Segmentation).
                        2. Cung cấp Pinyin và Nghĩa cho từng từ.
                        3. Trả về định dạng JSON List chính xác.
                        
                        Mẫu JSON:
                        [
                            {{"word": "我们", "pinyin": "wǒ men", "translation": "chúng tôi"}},
                            {{"word": "去", "pinyin": "qù", "translation": "đi"}},
                            {{"word": "学校", "pinyin": "xué xiào", "translation": "trường học"}}
                        ]
                        """
                        
                        # Gọi Gemini
                        # Lưu ý: Cần import model Gemini ở đầu file app.py hoặc lấy từ translator
                        genai_model = init_translator().model 
                        response = genai_model.generate_content(prompt_analysis)
                        
                        # Xử lý kết quả JSON
                        json_str = response.text.replace("```json", "").replace("```", "").strip()
                        processed_words = json.loads(json_str)
                        
                        # Tạo HTML (Giữ nguyên logic cũ của chị)
                        from translate_book import create_interactive_html_block # Đảm bảo đã import
                        
                        # Code cũ của chị cần hàm này, ta giả lập dữ liệu trả về cho khớp
                        # Logic cũ của chị hơi phức tạp, nhưng ta có thể gọi hàm tạo HTML trực tiếp
                        # Lưu ý: Chị cần kiểm tra file translate_book.py xem hàm create_interactive_html_block nhận tham số gì
                        # Giả sử nó nhận list các từ
                        
                        # Tạm thời dùng st.json để hiển thị kết quả (Debug)
                        # st.json(processed_words) 
                        
                        # --- TẠO GIAO DIỆN TƯƠNG TÁC (Viết lại đơn giản hơn cho Chị) ---
                        html_output = """
                        <style>
                            .word-container { display: inline-block; margin: 5px; text-align: center; cursor: pointer; }
                            .zh-word { font-size: 20px; font-weight: bold; color: #333; }
                            .pinyin { font-size: 12px; color: #666; }
                            .tooltip { visibility: hidden; background-color: black; color: #fff; text-align: center; padding: 5px; border-radius: 6px; position: absolute; z-index: 1; }
                            .word-container:hover .tooltip { visibility: visible; }
                        </style>
                        <div style='line-height: 1.5;'>
                        """
                        
                        for item in processed_words:
                            html_output += f"""
                            <div class="word-container" title="{item['translation']}">
                                <div class="pinyin">{item['pinyin']}</div>
                                <div class="zh-word">{item['word']}</div>
                            </div>
                            """
                        html_output += "</div>"
                        
                        st.success("Phân tích hoàn tất!")
                        components.html(html_output, height=600, scrolling=True)

                except Exception as e:
                    st.error(f"Lỗi phân tích AI: {e}")
                    st.info("Mẹo: Thử đoạn văn ngắn hơn hoặc kiểm tra API Key.")


def update_progress(progress, progress_bar, status_text):
    """Update the progress bar and status text"""
    progress_bar.progress(progress/100)  # Convert percentage to 0-1 range
    status_text.text(f"Processing... {progress:.1f}% completed")
    st.session_state.translation_progress = progress


def init_session():
    if 'client_ip' not in st.session_state:
        # Check if IP tracking is enabled in settings
        if st.secrets.get("enable_ip_tracking", False):
            try:
                # Get IP from Streamlit's request headers
                client_ip = None

                # Try to get the IP from X-Forwarded-For header first
                forwarded_for = st.request_header('X-Forwarded-For')
                if forwarded_for:
                    # X-Forwarded-For can contain multiple IPs, take the first one
                    client_ip = forwarded_for.split(',')[0].strip()

                # If no X-Forwarded-For, try X-Real-IP
                if not client_ip:
                    client_ip = st.request_header('X-Real-IP')

                # If still no IP, use a default
                st.session_state.client_ip = client_ip or '127.0.0.1'

            except Exception as e:
                print(f"Error getting IP: {e}")
                st.session_state.client_ip = '127.0.0.1'
        else:
            # If IP tracking is disabled, use a default value
            st.session_state.client_ip = '127.0.0.1'


def check_admin_password(password_attempt):
    return password_attempt == st.secrets["admin_password"]


def create_word_tooltip_html(processed_words, target_lang):
    """Create HTML with hover tooltips for each word"""
    # 添加类型检查
    if not processed_words or not isinstance(processed_words, (list, tuple)):
        raise ValueError("processed_words must be a non-empty list or tuple")
        
    with open('template.html', 'r', encoding='utf-8') as template_file:
        template_content = template_file.read()
    
    is_dark_theme = 'dark' in st.config.get_option('theme.base')
    
    content_html = f"""
    <div class="interactive-text" data-theme="{is_dark_theme}">
    """
    
    current_paragraph = []
    paragraphs = []
    
    # 添加错误处理
    try:
        # 按段落分组
        for word_data in processed_words:
            if not isinstance(word_data, dict):
                continue
                
            if word_data.get('word') == '\n':
                if current_paragraph:
                    paragraphs.append(current_paragraph)
                    current_paragraph = []
            else:
                current_paragraph.append(word_data)
        
        # 添加最后一个段落
        if current_paragraph:
            paragraphs.append(current_paragraph)
        
        # 生成 HTML
        for paragraph in paragraphs:
            content_html += "<p>"
            for word_data in paragraph:
                # 检查是否是标点符号
                is_punctuation = len(word_data.get('word', '')) == 1 and not word_data.get('pinyin')
                
                if is_punctuation:
                    content_html += f"""
                    <span class="non-chinese">{word_data['word']}</span>
                    """
                else:
                    content_html += f"""
                    <span class="interactive-word" 
                          onclick="speak('{word_data.get('word', '')}')"
                          data-tooltip="{word_data.get('pinyin', '')}&#10;{word_data.get('translation', '...')}">
                        {word_data.get('word', '')}
                    </span>
                    """
            content_html += "</p>"
        
    except Exception as e:
        st.error(f"Error processing text: {str(e)}")
        return None
    
    content_html += "</div>"
    
    final_html = template_content.replace('{{content}}', content_html)
    return final_html


def create_interactive_html(processed_words, include_english):
    """Create HTML content for interactive translation"""
    try:
        with open('template.html', 'r', encoding='utf-8') as template_file:
            html_content = template_file.read()
        
        # Add error checking for processed_words
        if processed_words is None:
            raise ValueError("processed_words cannot be None")
            
        # Create translation content with error handling
        translation_content = create_interactive_html_block(
            (None, [word for word in processed_words if word is not None]),  # Filter out None values
            include_english
        )
        
        if translation_content is None:
            raise ValueError("Failed to generate translation content")
            
        return html_content.replace('{{content}}', translation_content)
        
    except Exception as e:
        st.error(f"Error creating interactive HTML: {str(e)}")
        return None


def show_admin_interface():
    """Show admin interface with usage statistics"""
    st.title("Admin Dashboard")
    
    # Initialize password manager first
    if not init_password_manager():
        st.error("Failed to initialize password manager")
        return
        
    # Get usage statistics
    try:
        stats = pm.get_usage_stats()
        
        # Display overall statistics
        st.header("Overall Statistics")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Users", stats['total_users'])
        with col2:
            total_chars = sum(stats['daily_stats'].values())
            st.metric("Total Characters Translated", f"{total_chars:,}")
        
        # Daily usage graph
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
            fig.update_layout(
                title='Daily Translation Usage',
                xaxis_title='Date',
                yaxis_title='Characters Translated'
            )
            st.plotly_chart(fig)
        
        # User statistics
        st.header("User Statistics")
        for user, dates in stats['user_stats'].items():
            with st.expander(f"User: {user}"):
                user_df = pd.DataFrame(
                    list(dates.items()),
                    columns=['Date', 'Characters']
                )
                st.dataframe(user_df)
                
                # User usage graph
                fig = go.Figure(data=[
                    go.Scatter(
                        x=user_df['Date'],
                        y=user_df['Characters'],
                        mode='lines+markers',
                        name='Usage'
                    )
                ])
                fig.update_layout(
                    title=f'Usage Over Time - {user}',
                    xaxis_title='Date',
                    yaxis_title='Characters'
                )
                st.plotly_chart(fig)
    except Exception as e:
        st.error(f"Error loading statistics: {str(e)}")


def count_characters(text, include_english=True, second_language=None):
    """Count characters according to Azure Translator rules"""
    # Remove spaces and newlines
    text = text.replace(" ", "").replace("\n", "")
    # Count base characters
    char_count = len(text)
    
    # If both English and another language are selected, count twice
    if include_english and second_language and second_language != "English":
        char_count *= 2
        
    return char_count


def main():
    st.set_page_config(
        page_title="Translator App", 
        layout="centered",
        initial_sidebar_state="collapsed"
    )

    # Get URL parameters using st.query_params
    url_key = st.query_params.get('key', None)

    # Style configurations...
    st.markdown("""
    <style>
    .stTextArea textarea {
        cursor: text !important;
        caret-color: #1E90FF !important;
        color: inherit !important;
        background-color: transparent !important;
        font-size: 16px !important;
        line-height: 1.5 !important;
        border-radius: 4px !important;
        border: 1px solid rgba(128, 128, 128, 0.4) !important;
    }
    .stTextArea textarea:focus {
        border-color: #1E90FF !important;
        box-shadow: 0 0 0 1px #1E90FF !important;
    }
    
    /* Hide hamburger menu and footer by default */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Hide sidebar by default */
    section[data-testid="stSidebar"] {
        visibility: hidden;
        width: 0px;
    }
    
    /* Show sidebar when expanded */
    section[data-testid="stSidebar"][aria-expanded="true"] {
        visibility: visible;
        width: 300px;
    }
    
    /* Show sidebar toggle (hamburger menu) on hover */
    .css-1rs6os {
        visibility: visible;
        opacity: 0.1;
    }
    .css-1rs6os:hover {
        opacity: 1;
    }
    </style>
    """, unsafe_allow_html=True)

    # Initialize translator
    if 'translator' not in st.session_state:
        from translator import Translator
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
            if pm.check_password(url_key) and not pm.is_admin(url_key):
                st.session_state.user_logged_in = True
                st.session_state.current_user = url_key
                st.session_state.is_admin = False
                st.rerun()
            else:
                st.error("Invalid access key in URL")
                
        # Show regular login form if no URL key or invalid URL key
        st.title("Chinese Text Translator")
        user_password = st.text_input("Enter your access key", type="password", key="user_key")
        if st.button("Login"):
            if init_password_manager():
                if pm.check_password(user_password) and not pm.is_admin(user_password):
                    st.session_state.user_logged_in = True
                    st.session_state.current_user = user_password
                    st.session_state.is_admin = False
                    st.rerun()
                else:
                    st.error("Invalid access key")
    else:
        # Show logout button in sidebar only for admin
        if st.session_state.get('is_admin', False):
            with st.sidebar:
                if st.button("Logout"):
                    st.session_state.user_logged_in = False
                    st.session_state.current_user = None
                    st.session_state.is_admin = False
                    st.rerun()
            show_admin_interface()
        else:
            show_user_interface(st.session_state.current_user)


if __name__ == "__main__":
    main()

