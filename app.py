import streamlit as st
import requests
import re
from concurrent.futures import ThreadPoolExecutor
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

# 1. 带缓存机制的单词音标查询（极大提升二次查询速度）
@st.cache_data(ttl=3600, show_spinner=False)
def get_single_word_phonetic(word):
    clean_w = re.sub(r'[^a-zA-Z]', '', word).strip().lower()
    if not clean_w or len(clean_w) <= 1:  # 忽略单字母（如 a, I）提升效率
        return ""
    
    # 接口 1: Free Dictionary API (超时设为 1.5 秒)
    try:
        dict_res = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{clean_w}", timeout=1.5)
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

    # 接口 2: Datamuse API (备用接口，超时设为 1.5 秒)
    try:
        dm_res = requests.get(f"https://api.datamuse.com/words?sp={clean_w}&qe=sp&md=r&ipa=1", timeout=1.5)
        if dm_res.status_code == 200:
            dm_data = dm_res.json()
            if dm_data and "tags" in dm_data[0]:
                for tag in dm_data[0]["tags"]:
                    if tag.startswith("ipa_pron:"):
                        return f"/{tag.replace('ipa_pron:', '')}/"
    except Exception:
        pass

    return ""

# 2. 多线程并发提取英文音标（大幅缩短整句查询等待时间）
def get_text_phonetics_fast(text):
    words = re.findall(r"[a-zA-Z']+", text)
    if not words:
        return ""
    
    # 单个单词直接查
    if len(words) == 1:
        p = get_single_word_phonetic(words[0])
        return f"{words[0]} {p}" if p else words[0]
    
    # 整句多单词：使用 ThreadPoolExecutor 并发同时查询所有单词
    with ThreadPoolExecutor(max_workers=8) as executor:
        phonetics = list(executor.map(get_single_word_phonetic, words))
    
    # 组合结果
    results = []
    for w, p in zip(words, phonetics):
        if p:
            results.append(f"{w} {p}")
        else:
            results.append(w)
            
    return "  ".join(results)

# 查词/翻译核心逻辑
def get_translation_and_phonetic(query, langpair="en|zh-CN"):
    translation = "翻译服务暂时不可用"

    # 1. 翻译请求 (超时 3 秒)
    try:
        trans_res = requests.get(
            f"https://api.mymemory.translated.net/get?q={query}&langpair={langpair}", 
            timeout=3
        )
        if trans_res.status_code == 200:
            translation = trans_res.json()["responseData"]["translatedText"]
    except Exception:
        pass

    # 2. 并发快速获取英文音标
    if langpair.startswith("en"):
        phonetic = get_text_phonetics_fast(query)
    else:
        phonetic = get_text_phonetics_fast(translation) if translation != "翻译服务暂时不可用" else ""

    return phonetic, translation

# 三行清晰渲染展示（一行英文，一行音标，一行发音）
def display_result_and_save(query, phonetic, translation, is_english_input=True):
    st.markdown("---")
    st.subheader("查词 / 翻译结果")
    
    with st.container(border=True):
        p_text = phonetic if phonetic else "暂无音标"
        
        if is_english_input:
            # 英译中
            st.markdown(f"**【英文原文】**\n### {query}")
            st.markdown(f"**【对应音标】**\n`{p_text}`")
            st.write(f"**【中文释义】** {translation}")
            tts_word = query
            save_word = query
            save_trans = translation
        else:
            # 中译英
            st.markdown(f"**【中文原文】** {query}")
            st.markdown(f"**【英文翻译】**\n### {translation}")
            st.markdown(f"**【对应音标】**\n`{p_text}`")
            tts_word = translation
            save_word = translation
            save_trans = query

        # 一行展示语音播放
        st.markdown("**【语音发音】**")
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
        with st.spinner("正在快速翻译与获取音标..."):
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
        with st.spinner("正在快速翻译与获取音标..."):
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
            with st.spinner("正在快速翻译与获取音标..."):
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
        with st.expander(f"📌 {item['word']}"):
            st.markdown(f"**【音标】** `{item['phonetic']}`")
            st.write(f"**【释义】** {item['translation']}")
            st.audio(f"https://translate.google.com/translate_tts?ie=UTF-8&q={item['word']}&tl=en&client=tw-ob", format="audio/mp3")
            
            if st.button("删除", key=f"del_{idx}_{item['word']}"):
                st.session_state.vocab_list.pop(idx)
                st.rerun()
