import streamlit as st
import requests
import re
from concurrent.futures import ThreadPoolExecutor
import urllib.parse
import streamlit.components.v1 as components

# 页面配置
st.set_page_config(
    page_title="AI 随身英语全能助手",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 初始化 Session 状态
if "vocab_list" not in st.session_state:
    st.session_state.vocab_list = []

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "current_scenario" not in st.session_state:
    st.session_state.current_scenario = None

st.title("🤖 AI 随身英语全能助手")

# 功能选择菜单
app_mode = st.selectbox(
    "选择功能", 
    [
        "手动查词/翻译(自动识别)", 
        "🇨🇳 中文查英文", 
        "💬 AI 场景对话演练(一个月口语突破)",
        "📷 拍照识字/翻译"
    ]
)

# ==================== 核心辅助工具函数 ====================

# 多源保障语音播放组件（包含兼容性强的标准接口 + 本地引擎双重保障）
def play_audio(text, key_prefix="audio"):
    if not text or not text.strip():
        return
    
    clean_text = text.strip().replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace('\n', ' ')
    encoded_text = urllib.parse.quote(text.strip())
    
    # 采用高兼容 Google TTS 官方静态接口（支持绝大多数浏览器与移动端直接播放）
    google_audio_url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={encoded_text}&tl=en&client=tw-ob"
    
    html_code = f"""
    <div style="margin-top: 8px; margin-bottom: 8px;">
        <button onclick="playAudio_{key_prefix}()" style="
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 8px 18px;
            background-color: #007bff;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            box-shadow: 0 2px 4px rgba(0,0,0,0.15);
        ">
            🔊 点击标准发音
        </button>
        <script>
            function playAudio_{key_prefix}() {{
                // 方案 1: 使用直接音频对象播放 (兼容性最好，不被跨域阻断)
                var audio = new Audio("{google_audio_url}");
                var playPromise = audio.play();
                
                if (playPromise !== undefined) {{
                    playPromise.catch(function(error) {{
                        console.log("网络音频播放受阻，尝试系统自带引擎...", error);
                        // 方案 2: 降级使用 Web Speech API
                        if ('speechSynthesis' in window) {{
                            window.speechSynthesis.cancel();
                            var msg = new SpeechSynthesisUtterance("{clean_text}");
                            msg.lang = 'en-US';
                            msg.rate = 0.85;
                            window.speechSynthesis.speak(msg);
                        }} else {{
                            alert("请检查设备是否开启静音模式，或尝试使用 Chrome/Edge 浏览器打开。");
                        }}
                    }});
                }}
            }}
        </script>
    </div>
    """
    components.html(html_code, height=55)

# 1. 带缓存机制的单词音标查询
@st.cache_data(ttl=3600, show_spinner=False)
def get_single_word_phonetic(word):
    clean_w = re.sub(r'[^a-zA-Z]', '', word).strip().lower()
    if not clean_w or len(clean_w) <= 1:
        return ""
    
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

# 2. 多线程并发提取整句音标
def get_text_phonetics_fast(text):
    words = re.findall(r"[a-zA-Z']+", text)
    if not words:
        return ""
    
    if len(words) == 1:
        p = get_single_word_phonetic(words[0])
        return f"{words[0]} {p}" if p else words[0]
    
    with ThreadPoolExecutor(max_workers=8) as executor:
        phonetics = list(executor.map(get_single_word_phonetic, words))
    
    results = []
    for w, p in zip(words, phonetics):
        if p:
            results.append(f"{w} {p}")
        else:
            results.append(w)
            
    return "  ".join(results)

# 3. 查词与翻译核心逻辑
def get_translation_and_phonetic(query, langpair="en|zh-CN"):
    translation = "翻译服务暂时不可用"

    try:
        trans_res = requests.get(
            f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(query)}&langpair={langpair}", 
            timeout=3
        )
        if trans_res.status_code == 200:
            translation = trans_res.json()["responseData"]["translatedText"]
    except Exception:
        pass

    if langpair.startswith("en"):
        phonetic = get_text_phonetics_fast(query)
    else:
        phonetic = get_text_phonetics_fast(translation) if translation != "翻译服务暂时不可用" else ""

    return phonetic, translation

# 4. 结果渲染与生词卡保存
def display_result_and_save(query, phonetic, translation, is_english_input=True):
    st.markdown("---")
    st.subheader("查词 / 翻译结果")
    
    with st.container(border=True):
        p_text = phonetic if phonetic else "暂无音标"
        
        if is_english_input:
            st.markdown(f"**【英文原文】**\n### {query}")
            st.markdown(f"**【对应音标】**\n`{p_text}`")
            st.write(f"**【中文释义】** {translation}")
            tts_word = query
            save_word = query
            save_trans = translation
        else:
            st.markdown(f"**【中文原文】** {query}")
            st.markdown(f"**【英文翻译】**\n### {translation}")
            st.markdown(f"**【对应音标】**\n`{p_text}`")
            tts_word = translation
            save_word = translation
            save_trans = query

        st.markdown("**【语音发音】**")
        play_audio(tts_word, key_prefix=f"res_{abs(hash(tts_word))}")

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

# ==================== 3. 💬 AI 场景对话演练 ====================
elif app_mode == "💬 AI 场景对话演练(一个月口语突破)":
    st.subheader("💬 AI 场景对话演练")
    st.info("💡 建议每天演练 1 个场景！选择场景后，AI 角色会主动说话，输入你的英文回答即可开始对话。")

    scenarios = {
        "👋 日常社交：与外国同事打招呼/闲聊": {
            "role": "John (Colleague)",
            "init_msg": "Hey! Good morning! How was your weekend?",
            "zh_init": "嘿！早上好！你周末过得怎么样？"
        },
        "🏭 现场工作：确认生产/工作进度": {
            "role": "Manager",
            "init_msg": "Hi, could you give me a quick update on today's schedule?",
            "zh_init": "嗨，能简单跟我汇报一下今天的日程安排/进度吗？"
        },
        "☕ 咖啡厅/餐厅点餐与结账": {
            "role": "Barista / Waiter",
            "init_msg": "Hello! Welcome! What can I get started for you today?",
            "zh_init": "你好！欢迎光临！今天想喝点什么？"
        },
        "✈️ 机场/海关过关问答": {
            "role": "Customs Officer",
            "init_msg": "Good day. What is the purpose of your visit today?",
            "zh_init": "你好。请问你这次入境的目的是什么？"
        },
        "🚕 乘车问路与目的地确认": {
            "role": "Taxi Driver",
            "init_msg": "Hi there! Where are you heading to today?",
            "zh_init": "嗨你好！今天要去哪里？"
        }
    }

    selected_scenario = st.selectbox("选择对话场景：", list(scenarios.keys()))

    if st.session_state.current_scenario != selected_scenario:
        st.session_state.current_scenario = selected_scenario
        init_data = scenarios[selected_scenario]
        st.session_state.chat_history = [
            {
                "sender": "ai", 
                "role": init_data["role"],
                "text": init_data["init_msg"], 
                "zh": init_data["zh_init"],
                "phonetic": get_text_phonetics_fast(init_data["init_msg"])
            }
        ]

    if st.button("🔄 重新开始本场景对话"):
        init_data = scenarios[selected_scenario]
        st.session_state.chat_history = [
            {
                "sender": "ai", 
                "role": init_data["role"],
                "text": init_data["init_msg"], 
                "zh": init_data["zh_init"],
                "phonetic": get_text_phonetics_fast(init_data["init_msg"])
            }
        ]
        st.rerun()

    st.markdown("---")

    for idx, msg in enumerate(st.session_state.chat_history):
        if msg["sender"] == "ai":
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(f"**{msg['role']}**: {msg['text']}")
                st.caption(f"🔊 音标: `{msg['phonetic']}`")
                st.caption(f"💡 中文含义: {msg['zh']}")
                play_audio(msg['text'], key_prefix=f"ai_{idx}")
        else:
            with st.chat_message("user", avatar="👤"):
                st.markdown(f"**你**: {msg['text']}")
                if "suggestion" in msg and msg["suggestion"]:
                    st.info(f"✨ **地道表达建议**: {msg['suggestion']}\n\n🔊 **建议音标**: `{msg['sug_phonetic']}`")
                    play_audio(msg['suggestion'], key_prefix=f"sug_{idx}")

    user_reply = st.chat_input("用英文回答（例如：It was great, I rested at home.）")

    if user_reply and user_reply.strip():
        with st.spinner("AI 正在思考回复并分析口语表达..."):
            if any('\u4e00' <= char <= '\u9fff' for char in user_reply):
                sug_p, sug_eng = get_translation_and_phonetic(user_reply, langpair="zh-CN|en")
                user_eng = sug_eng
            else:
                user_eng = user_reply
                sug_p, sug_eng = get_translation_and_phonetic(user_reply, langpair="en|zh-CN")
                _, sug_eng = get_translation_and_phonetic(sug_eng, langpair="zh-CN|en")

            st.session_state.chat_history.append({
                "sender": "user",
                "text": user_reply,
                "suggestion": sug_eng,
                "sug_phonetic": get_text_phonetics_fast(sug_eng)
            })

            ai_next_text = f"Got it! Thanks for telling me. Anything else I can help you with?"
            ai_next_p = get_text_phonetics_fast(ai_next_text)
            _, ai_next_zh = get_translation_and_phonetic(ai_next_text, langpair="en|zh-CN")

            st.session_state.chat_history.append({
                "sender": "ai",
                "role": scenarios[selected_scenario]["role"],
                "text": ai_next_text,
                "zh": ai_next_zh,
                "phonetic": ai_next_p
            })

            st.rerun()

# ==================== 4. 📷 拍照识字/翻译 ====================
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

# ==================== 5. 我的生词本 ====================
st.markdown("---")
st.subheader("📖 我的生词本")

if not st.session_state.vocab_list:
    st.info("暂无生词，快在上方查询并添加吧！")
else:
    for idx, item in enumerate(list(st.session_state.vocab_list)):
        with st.expander(f"📌 {item['word']}"):
            st.markdown(f"**【音标】** `{item['phonetic']}`")
            st.write(f"**【释义】** {item['translation']}")
            play_audio(item['word'], key_prefix=f"vocab_{idx}")
            
            if st.button("删除", key=f"del_{idx}_{item['word']}"):
                st.session_state.vocab_list.pop(idx)
                st.rerun()
