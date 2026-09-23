# Suggest Reply Bot

Discord AI 建議回覆 Bot。

支援 OpenAI-compatible API。

每個 Discord 使用者都有獨立的：

- API URL
- API Key
- Model

## 指令

### /set_api

設定 API URL 與 API Key。

設定完成後會自動取得模型列表，
再使用 Discord 下拉選單選擇模型。

### /set_model

重新取得模型列表並選擇模型。

### /reply

直接輸入對方訊息，
產生三種建議回答。

### 建議回覆

在 Discord 對訊息按右鍵：

Apps → 建議回覆

Bot 會取得最近聊天紀錄，
分析對方狀態與使用者聊天方式，
產生：

- 自然
- 關心
- 延續話題

三種回答。

## 使用者資料

設定會使用 Discord User ID 綁定。

每個使用者的：

- API URL
- API Key
- Model

彼此獨立。

原本的 user_keys.db 會自動加入新的欄位，
保留原有的 Discord User ID 與 API Key。

## API 格式

API 必須支援 OpenAI-compatible API：

GET：

/models

POST：

/chat/completions