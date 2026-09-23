from google import genai

# =========================================================
# Gemini API Core Call (保留動態模型搜尋與 Fallback 機制)
# =========================================================
def call_gemini_api(api_key: str, prompt: str) -> str:
    client = genai.Client(api_key=api_key)
    candidate_models = ["gemini-3-flash", "gemini-3.6-flash", "gemini-flash-latest"]
    
    last_err = None
    for m in candidate_models:
        try:
            res = client.models.generate_content(model=m, contents=prompt)
            if res.text:
                return res.text.strip()
        except Exception as e:
            last_err = e
            continue

    try:
        models = list(client.models.list())
        for model in models:
            m_name = getattr(model, "name", "")
            supported_actions = getattr(model, "supported_actions", [])
            if "generateContent" in supported_actions and "flash" in m_name.lower():
                try:
                    res = client.models.generate_content(model=m_name, contents=prompt)
                    if res.text:
                        return res.text.strip()
                except Exception:
                    continue
    except Exception:
        pass

    raise Exception(f"無法存取 Gemini API：{last_err}")


# =========================================================
# Jev 雙階段 Pipeline
# =========================================================
def run_jev_two_stage_pipeline(api_key: str, context_text: str) -> str:
    # 階段 1：Jev 意圖與策略分析
    jev_analysis_prompt = f"""
你是一個精通社交心理與網路對話的 Jev 社交分析引擎。
請對以下的 Discord 對話進行深度意圖解讀：

---
{context_text}
---

請輸出一段 Jev 分析結果，包含：
1. 【對方真實意圖】（如：尋求認同、開玩笑嗆人、無聊發廢文、試探性問問題）。
2. 【建議社交策略】（如：冷處理、順著接梗、反嗆回去、簡單回覆、極簡敷衍）。
3. 【語氣指令】給回覆 AI 的具體撰寫指導。

請直接輸出 Jev 分析與語氣指令，不要包含其他贅詞。
"""
    jev_strategy = call_gemini_api(api_key, jev_analysis_prompt)

    # 階段 2：根據 Jev 策略生成台灣年輕人口吻回覆
    gemini_generation_prompt = f"""
你是 18 歲的台灣年輕人，正躺在沙發上滑 Discord 跟朋友聊天。

【Jev 引擎分析結果與社交策略】
{jev_strategy}

【對話背景】
{context_text}

【語氣風格指南】
1. 極度簡短：1~15 個字內解決，能用幾個字表達就絕不多寫。
2. 真人隨意感：多用「欸、亂講、真的假、笑死、確實、好啊、無聊、還行」。
3. 標點規範：禁止使用驚嘆號「！」，句尾不要加句號，盡量不使用 Emoji。
4. 禁用 AI 罐頭詞：嚴禁「嗨嗨、很高興、超讚、當然、沒問題、很高興能為您提供服務」。
5. 直接輸出：不換行，不要引號，不要做任何補充或解釋，直接給出傳送內容。
"""
    final_reply = call_gemini_api(api_key, gemini_generation_prompt)
    return final_reply
