import streamlit as st
import requests
import re
from io import BytesIO
import PIL.Image as Image

# 页面配置
st.set_page_config(
    page_title="AI 随身英语全能助手",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 初始化 Session 生词本
if "vocab_list" not in st.session_state:
    st.session_state.vocab_list = []

st.title("🤖 AI 随身英语全能助手")

# 功能选择菜单
app_mode = st.selectbox(
    "选择功能", 
    ["手动查词/翻译(自动识别)", "🇨🇳 中文查英文", "📷 拍照识字/翻译"]
)

# 精准查询单个英文单词音标（双接口容错）
def get_single_word_phonetic(word):
    # 清理非英文字母
    clean_w = re.sub(r'[^a-zA-1]', '', word).strip().lower()
    if not clean_w:
        return ""
    
    # 尝试接口 1: Dictionary API
    try:
        dict_res = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{clean_w}", timeout=3)
        if dict_res.status_code == 200:
            dict_data = dict_res.json()
            p = dict_data[0].get("phonetic", "")
            if not p:
                for item in dict_data[0].get("phonetics", []):
                    if item.get("text"):
                        p = item["text"]
                        break
            if p:
                return p
    except Exception:
        pass

    # 尝试接口 2: Datamuse API (备用)
    try:
        dm_res = requests.get(f"https://api.datamuse.com/words?sp={clean_w}&qe=sp&md=r&ipa=1", timeout=3)
        if dm_res.status_code == 200:
            dm_data = dm_res.json()
            if dm_data and "tags" in dm_data[0]:
                for tag in dm_data[0]["tags"]:
                    if tag.startswith("ipa_pron:"):
                        return f"/{tag.replace('ipa_pron:', '')}/"
    except Exception:
        pass

    return ""

# 提取英文文本中的音标（支持单词和短语）
def get_text_phonetics(text):
    # 提取所有英文单词
    words = re.findall(r'[a-zA-Z]+', text)
    if not words:
        return ""
    
    # 如果是单个词
    if len(words) == 1:
        p = get_single_word_phonetic(words[0])
        return p if p else ""
    
    # 如果是短语，查询前 3 个核心词的音标组合
    results = []
    for w in words[:3]:
        p = get_single_word_phonetic(w)
        if p:
            results.append(f"{w} {p}")
            
    return " | ".join(results) if results else ""

# 查词/翻译核心逻辑
def get_translation_and_phonetic(query, langpair="en|zh-CN"):
    translation = "翻译服务暂时不可用"

    # 1. 翻译
    try:
        trans_res = requests.get(
            f"https://api.mymemory.translated.net/get?q={query}&langpair={langpair}", 
            timeout=5
        )
        if trans_res.status_code == 200:
            translation = trans_res.json()["responseData"]["translatedText"]
    except Exception:
        pass

    # 2. 获取英文部分的音标
    if langpair.startswith("en"):
        # 英译中：获取输入英文的音标
        phonetic = get_text_phonetics(query)
    else:
        # 中译英：获取翻译结果英文的音标
        phonetic = get_text_phonetics(translation) if translation != "翻译服务暂时不可用" else ""

    return phonetic, translation

# 渲染卡片与保存
def display_result_and_save(query, phonetic, translation, is_english_input=True):
    st.markdown("---")
    st.subheader("查词 / 翻译结果")
    
    with st.container(border=True):
        if is_english_input:
            # 英译中
            p_text = phonetic if phonetic else "暂无音标"
            st.write(f"### {query}")
            st.info(f"🔊 音标：**{p_text}**")
            st.write(f"**中文释义：** {translation}")
            tts_word = query
            save_word = query
            save_trans = translation
        else:
            # 中译英
            p_text = phonetic if phonetic else "暂无音标"
            st.write(f"### 英文翻译：{translation}")
            st.info(f"🔊 英文音标：**{p_text}**")
            st.write(f"**中文原文：** {query}")
            tts_word = translation
            save_word = translation
            save_trans = query

        # 发音组件
        audio_url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={tts_word}&tl=en&client=tw-ob"
        st.audio(audio_url, format="audio/mp3")

        # 生词本保存
        if st.button("➕ 保存到我的生词本", key=f"save_{save_word}"):
            item = {"word": save_word, "phonetic": p_text, "translation": save_trans}
            if not any(v['word'].lower() == save_word.lower() for v in st.session_state.vocab_list):
                st.session_state.vocab_list.insert(0, item)
                st.success("已成功保存到生词本！")
            else:
                st.warning("该单词已存在于生词本中。")

# ==================== 1. 手动查词/翻译 (自动识别中英) ====================
if app_mode == "手动查词/翻译(自动识别)":
    user_input = st.text_area("输入英文或中文词句：", placeholder="例如: Apple 或 学习英语很有趣", height=100)
    col1, col2 = st.columns([2, 1])
    with col1:
        search_btn = st.button("🔍 查询 / 翻译", type="primary")
    with col2:
        if st.button("🗑️ 清空"): 
            st.rerun()

    if search_btn and user_input.strip():
        if any('\u4e00' <= char <= '\u9fff' for char in user_input):
            phonetic, translation = get_translation_and_phonetic(user_input, langpair="zh-CN|en")
            display_result_and_save(user_input, phonetic, translation, is_english_input=False)
        else:
            phonetic, translation = get_translation_and_phonetic(user_input, langpair="en|zh-CN")
            display_result_and_save(user_input, phonetic, translation, is_english_input=True)

# ==================== 2. 🇨🇳 中文查英文 ====================
elif app_mode == "🇨🇳 中文查英文":
    user_input = st.text_area("输入你想查询的中文词汇或句子：", placeholder="例如: 苹果、开心、今天天气很好", height=100)
    col1, col2 = st.columns([2, 1])
    with col1:
        search_btn = st.button("🔍 查询英文及音标发音", type="primary")
    with col2:
        if st.button("🗑️ 清空"): 
            st.rerun()

    if search_btn and user_input.strip():
        phonetic, translation = get_translation_and_phonetic(user_input, langpair="zh-CN|en")
        display_result_and_save(user_input, phonetic, translation, is_english_input=False)

# ==================== 3. 📷 拍照识字/翻译 ====================
elif app_mode == "📷 拍照识字/翻译":
    st.write("拍摄包含文字的图片。")
    uploaded_file = st.camera_input("拍照")

    if uploaded_file is not None:
        with st.spinner("正在解析图片文字..."):
            try:
                files = {'file': ('image.jpg', uploaded_file.getvalue(), 'image/jpeg')}
                data = {'apikey': 'helloworld', 'language': 'eng'}
                ocr_res = requests.post('https://api.ocr.space/parse/image', files=files, data=data, timeout=10)
                
                result_json = ocr_res.json()
                recognized_text = result_json.get("ParsedResults", [{}])[0].get("ParsedText", "").strip()
            except Exception:
                recognized_text = ""

        if recognized_text:
            st.success(f"识别到文字: {recognized_text}")
            if any('\u4e00' <= char <= '\u9fff' for char in recognized_text):
                phonetic, translation = get_translation_and_phonetic(recognized_text, langpair="zh-CN|en")
                display_result_and_save(recognized_text, phonetic, translation, is_english_input=False)
            else:
                phonetic, translation = get_translation_and_phonetic(recognized_text, langpair="en|zh-CN")
                display_result_and_save(recognized_text, phonetic, translation, is_english_input=True)
        else:
            st.warning("未能识别到清晰文字，请重新对焦拍摄。")

# ==================== 4. 我的生词本 ====================
st.markdown("---")
st.subheader("📖 我的生词本")

if not st.session_state.vocab_list:
    st.info("暂无生词，快在上方查询并添加吧！")
else:
    for idx, item in enumerate(list(st.session_state.vocab_list)):
        with st.expander(f"📌 {item['word']}  [{item['phonetic']}]"):
            st.write(f"**释义：** {item['translation']}")
            st.audio(f"https://translate.google.com/translate_tts?ie=UTF-8&q={item['word']}&tl=en&client=tw-ob", format="audio/mp3")
            
            if st.button("删除", key=f"del_{idx}_{item['word']}"):
                st.session_state.vocab_list.pop(idx)
                st.rerun()
                
