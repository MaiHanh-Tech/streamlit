import streamlit as st
import os
from translate_book import translate_file, create_interactive_html_block
from password_manager import PasswordManager
import streamlit.components.v1 as components
import jieba
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    return st.session_state.translator

def count_characters(text, include_english=True, second_language=None):
    text = text.replace(" ", "").replace("\n", "")
    char_count = len(text)
    if include_english and second_language and second_language != "English":
        char_count *= 2
    return char_count

def update_progress(progress, progress_bar, status_text):
    progress_bar.progress(progress/100)
    status_text.text(f"Processing... {progress:.1f}% completed")

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
            "Vietnamese": "vi",
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
            "Uzbek": "uz"
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
        example_text = """第37届中国电影金鸡奖是2024年11月16日在中国厦门举行的中国电影颁奖礼。"""
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
            chars_count = count_characters(text_input, include_english, second_language)
            if not pm.check_usage_limit(st.session_state.current_user, chars_count):
                daily_limit = pm.get_user_limit(st.session_state.current_user)
                st.error(f"You have exceeded your daily translation limit ({daily_limit:,} characters). Please try again tomorrow.")
                return
            
            pm.track_usage(st.session_state.current_user, chars_count)
            
            # Show usage
            daily_usage = pm.get_daily_usage(st.session_state.current_user)
            daily_limit = pm.get_user_limit(st.session_state.current_user)
            st.info(f"Today's usage: {daily_usage:,}/{daily_limit:,} characters")
            
            # --- INTERACTIVE MODE ---
            if translation_mode == "Interactive Word-by-Word":
                try:
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    status_text.text("Step 1/3: Segmenting text...")
                    progress_bar.progress(10)
                    
                    # Split logic using Jieba (Original)
                    paragraphs = text_input.split('\n')
                    all_words = []
                    
                    for paragraph in paragraphs:
                        if paragraph.strip():
                            # Jieba cut
                            tokens = list(jieba.tokenize(paragraph))
                            words = [token[0] for token in tokens]
                            all_words.extend(words)
                        else:
                            all_words.append('\n')
                    
                    total_words = len(all_words)
                    status_text.text("Step 2/3: Processing words...")
                    processed_words = [None] * total_words 
                    
                    # Function to process batch
                    def process_word_batch(word_batch, start_index, translator):
                        results = []
                        for i, word in enumerate(word_batch):
                            try:
                                if word == '\n':
                                    results.append((start_index + i, {'word': '\n'}))
                                elif word.strip():
                                    # Call Gemini via Translator
                                    result = translator.process_chinese_text(
                                        word, 
                                        languages[second_language]
                                    )
                                    word_dict = {'word': word, 'pinyin': '', 'translations': []}
                                    if result and len(result) > 0:
                                        word_dict.update(result[0])
                                    results.append((start_index + i, word_dict))
                                else:
                                    results.append((start_index + i, {'word': '', 'pinyin': '', 'translations': []}))
                            except:
                                results.append((start_index + i, {'word': word, 'pinyin': '', 'translations': []}))
                        return results
                    
                    # Batch processing
                    batch_size = 5
                    batches = []
                    for i in range(0, len(all_words), batch_size):
                        batch = all_words[i:i + batch_size]
                        batches.append((i, batch))
                    
                    with ThreadPoolExecutor(max_workers=5) as executor:
                        futures = []
                        for start_idx, batch in batches:
                            future = executor.submit(process_word_batch, batch, start_idx, translator)
                            futures.append(future)
                        
                        completed = 0
                        for future in as_completed(futures):
                            for idx, result in future.result():
                                processed_words[idx] = result
                            completed += 1
                            progress_bar.progress(int(10 + (completed / len(batches) * 60)))

                    # Step 3: Generate HTML
                    status_text.text("Step 3/3: Generating interactive HTML...")
                    progress_bar.progress(80)
                    
                    # Load template and replace
                    with open('template.html', 'r', encoding='utf-8') as template_file:
                        html_template = template_file.read()
                        
                    translation_content = create_interactive_html_block(
                        (text_input, [w for w in processed_words if w is not None]),
                        include_english
                    )
                    
                    final_html = html_template.replace('{{content}}', translation_content)
                    
                    progress_bar.progress(100)
                    status_text.text("Translation completed!")
                    
                    st.success("Translation completed!")
                    st.download_button(
                        label="Download HTML",
                        data=final_html.encode('utf-8'),
                        file_name="translation.html",
                        mime="text/html; charset=utf-8"
                    )
                    components.html(final_html, height=800, scrolling=True)
                    
                except Exception as e:
                    st.error(f"Interactive mode error: {str(e)}")

            # --- STANDARD MODE ---
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Gọi hàm từ translate_book.py
                html_content = translate_file(
                    text_input,
                    lambda p: update_progress(p, progress_bar, status_text),
                    include_english,
                    languages[second_language], # Truyền mã ngôn ngữ (ví dụ 'vi')
                    pinyin_style,
                    translation_mode
                )
                
                st.success("Translation completed!")
                st.download_button(
                    label="Download HTML",
                    data=html_content,
                    file_name="translation.html",
                    mime="text/html"
                )
                components.html(html_content, height=800, scrolling=True)
            
        except Exception as e:
            st.error(f"Translation error: {str(e)}")

def show_admin_interface(admin_password):
    st.title("Admin Dashboard")
    if not init_password_manager(): return
    try:
        stats = pm.get_usage_stats()
        st.header("Overall Statistics")
        col1, col2 = st.columns(2)
        with col1: st.metric("Total Users", stats['total_users'])
        with col2:
            total_chars = sum(sum(dates.values()) for dates in stats['user_stats'].values())
            st.metric("Total Characters", f"{total_chars:,}")
        
        st.header("Daily Usage")
        daily_df = pd.DataFrame(list(stats['daily_stats'].items()), columns=['Date', 'Characters'])
        if not daily_df.empty:
            fig = go.Figure(data=[go.Bar(x=daily_df['Date'], y=daily_df['Characters'])])
            st.plotly_chart(fig)
            
    except Exception as e: st.error(f"Error: {str(e)}")

def main():
    st.set_page_config(page_title="Translator App", layout="centered", initial_sidebar_state="collapsed")
    url_key = st.query_params.get('key', None)

    if 'translator' not in st.session_state:
        st.session_state.translator = Translator()

    with st.sidebar:
        st.title("Admin Access")
        admin_pass = st.text_input("Enter admin key", type="password", key="admin_key")
        if st.button("Login as Admin"):
            if init_password_manager() and pm.is_admin(admin_pass):
                st.session_state.user_logged_in = True
                st.session_state.current_user = admin_pass
                st.session_state.is_admin = True
                st.rerun()

    if not st.session_state.get('user_logged_in', False):
        if url_key and init_password_manager():
            if pm.check_password(url_key) and not pm.is_admin(url_key):
                st.session_state.user_logged_in = True
                st.session_state.current_user = url_key
                st.session_state.is_admin = False
                st.rerun()
                
        st.title("Chinese Text Translator")
        user_pass = st.text_input("Enter your access key", type="password", key="user_key")
        if st.button("Login"):
            if init_password_manager():
                if pm.check_password(user_pass) and not pm.is_admin(user_pass):
                    st.session_state.user_logged_in = True
                    st.session_state.current_user = user_pass
                    st.session_state.is_admin = False
                    st.rerun()
                else: st.error("Invalid access key")
    else:
        if st.session_state.get('is_admin', False):
            show_admin_interface(st.session_state.current_user)
        else:
            show_user_interface(st.session_state.current_user)

if __name__ == "__main__":
    main()
