import streamlit as st
import requests
from paddleocr import PaddleOCR
import speech_recognition as sr
from io import BytesIO
import PIL.Image as Image

# 页面配置
st.set_page_config(
    page_title="AI 随身英语全能助手",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 初始化 OCR 模型
@st.cache_resource
def load_ocr_model():
    return PaddleOCR(use_angle_cls=True, lang="ch")

ocr_model = load_ocr_model()
r = sr.Recognizer()

# 初始化生词本
if "vocab_list" not in st.session_state:
    st.session_state.vocab_list = []

st.title("🤖 AI 随身英语全能助手")

# 1. 功能选择
app_mode = st.selectbox("选择功能", ["手动查词/翻译", "📷 拍照识字/翻译", "🎙️ 语音输入(中->英)"])

# 通用翻译函数
def get_translation_and_phonetic(query, langpair="en|zh-CN"):
    is_single_word = len(query.split()) == 1 and "|" not in langpair
    phonetic = ""
    translation = "翻译服务暂时不可用"

    if is_single_word and langpair.startswith("en"):
        try:
            dict_res = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{query}", timeout=5)
            if dict_res.status_code == 200:
                dict_data = dict_res.json()
                phonetic = dict_data[0].get("phonetic", "")
                if not phonetic:
                    for p in dict_data[0].get("phonetics", []):
                        if "text" in p and p["text"]:
                            phonetic = p["text"]
                            break
        except Exception:
            pass

    try:
        trans_res = requests.get(
            f"https://api.mymemory.translated.net/get?q={query}&langpair={langpair}", 
            timeout=5
        )
        if trans_res.status_code == 200:
            translation = trans_res.json()["responseData"]["translatedText"]
    except Exception:
        pass

    return phonetic, translation, is_single_word

# 纯原生 Streamlit 渲染结果卡片（防止 DOM removeChild 报错）
def display_result_and_save(query, phonetic, translation, is_single_word, is_english_input=True):
    display_phonetic = phonetic if phonetic else ("/暂无音标/" if is_single_word else "")
    
    st.markdown("---")
    st.subheader("查词 / 翻译结果")
    
    # 使用纯原生原生容器卡片
    with st.container(border=True):
        st.write(f"### {query}  `{display_phonetic}`")
        st.write(f"**释义：** {translation}")
        
        # 播放发音
        tts_query = query if is_english_input else translation
        audio_url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={tts_query}&tl=en&client=tw-ob"
        st.audio(audio_url, format="audio/mp3")

        # 保存生词本
        if is_english_input:
            if st.button("➕ 保存到我的生词本", key=f"save_{query}"):
                item = {"word": query, "phonetic": display_phonetic, "translation": translation}
                if not any(v['word'].lower() == query.lower() for v in st.session_state.vocab_list):
                    st.session_state.vocab_list.insert(0, item)
                    st.success("已成功保存到生词本！")
                else:
                    st.warning("该单词已存在于生词本中。")

# ==================== 1. 手动查词/翻译 ====================
if app_mode == "手动查词/翻译":
    user_input = st.text_area("输入英文单词或句子（自动识别中英）：", placeholder="例如: Apple 或 Learning English is fun!", height=100)
    col1, col2 = st.columns([2, 1])
    with col1:
        search_btn = st.button("🔍 查询 / 翻译", type="primary")
    with col2:
        if st.button("🗑️ 清空"): 
            st.rerun()

    if search_btn and user_input.strip():
        if any('\u4e00' <= char <= '\u9fff' for char in user_input):
            phonetic, translation, is_single_word = get_translation_and_phonetic(user_input, langpair="zh-CN|en")
            display_result_and_save(user_input, phonetic, translation, is_single_word, is_english_input=False)
        else:
            phonetic, translation, is_single_word = get_translation_and_phonetic(user_input, langpair="en|zh-CN")
            display_result_and_save(user_input, phonetic, translation, is_single_word, is_english_input=True)

# ==================== 2. 📷 拍照识字/翻译 ====================
elif app_mode == "📷 拍照识字/翻译":
    st.write("拍摄包含英文单词或句子的图片。")
    uploaded_file = st.camera_input("拍照")

    if uploaded_file is not None:
        image = Image.open(uploaded_file)
        with st.spinner("正在识别图片中的文字..."):
            img_bytes = uploaded_file.getvalue()
            result = ocr_model.ocr(img_bytes, cls=True)
            
            recognized_text = ""
            if result:
                for idx in range(len(result)):
                    res = result[idx]
                    if res:
                        for line in res:
                            recognized_text += line[1][0] + " "

        recognized_text = recognized_text.strip()
        
        if recognized_text:
            st.success(f"识别到文字: {recognized_text}")
            if any('\u4e00' <= char <= '\u9fff' for char in recognized_text):
                phonetic, translation, is_single_word = get_translation_and_phonetic(recognized_text, langpair="zh-CN|en")
                display_result_and_save(recognized_text, phonetic, translation, is_single_word, is_english_input=False)
            else:
                phonetic, translation, is_single_word = get_translation_and_phonetic(recognized_text, langpair="en|zh-CN")
                display_result_and_save(recognized_text, phonetic, translation, is_single_word, is_english_input=True)
        else:
            st.warning("未能在图片中识别到文字。")

# ==================== 3. 🎙️ 语音输入(中->英) ====================
elif app_mode == "🎙️ 语音输入(中->英)":
    st.write("点击下方按钮，开始说中文。")
    audio_data = st.experimental_audio_input("按住说话")

    if audio_data is not None:
        with st.spinner("正在识别您的语音(中文)..."):
            try:
                with sr.AudioFile(BytesIO(audio_data.getvalue())) as source:
                    audio_content = r.record(source)
                
                recognized_chinese = r.recognize_google(audio_content, language="zh-CN")
                st.success(f"识别到您说: {recognized_chinese}")
                
                with st.spinner("正在翻译成英文..."):
                    phonetic, translation, is_single_word = get_translation_and_phonetic(recognized_chinese, langpair="zh-CN|en")
                    
                    st.markdown("---")
                    st.subheader("英文翻译结果")
                    with st.container(border=True):
                        st.write(f"### {translation}")
                        st.write(f"（原文：{recognized_chinese}）")
                        st.audio(f"https://translate.google.com/translate_tts?ie=UTF-8&q={translation}&tl=en&client=tw-ob", format="audio/mp3")

            except sr.UnknownValueError:
                st.error("未能听懂您的语音，请重试。")
            except sr.RequestError as e:
                st.error(f"语音识别服务请求失败: {e}")
            except Exception as e:
                st.error(f"发生错误: {e}")

# ==================== 4. 本地生词本展示 ====================
st.markdown("---")
st.subheader("📖 我的生词本")

if not st.session_state.vocab_list:
    st.info("暂无生词，快在上方查询并添加吧！")
else:
    # 遍历列表时使用副本 iterator 避免 IndexError
    for idx, item in enumerate(list(st.session_state.vocab_list)):
        with st.expander(f"📌 {item['word']}  {item['phonetic']}"):
            st.write(f"**释义：** {item['translation']}")
            st.audio(f"https://translate.google.com/translate_tts?ie=UTF-8&q={item['word']}&tl=en&client=tw-ob", format="audio/mp3")
            
            if st.button("删除", key=f"del_{idx}_{item['word']}"):
                st.session_state.vocab_list.pop(idx)
                st.rerun()
        
