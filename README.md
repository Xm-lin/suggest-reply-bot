# Suggest Reply Bot

Discord AI 建議回覆 Bot。

支援 OpenAI-compatible API。

每個 Discord 使用者都有獨立的：

- API URL
- API Key
- Model

## 指令
<img width="921" height="247" alt="image" src="https://github.com/user-attachments/assets/35bd1cf0-920b-482b-86b7-8ae5aba8be2e" />
### /set_api
<img width="704" height="662" alt="image" src="https://github.com/user-attachments/assets/bf4cbb86-a75e-40b8-ba97-b4d5f4f58084" />
設定 API URL 與 API Key。

設定完成後會自動取得模型列表，
再使用 Discord 下拉選單選擇模型。
<img width="708" height="479" alt="image" src="https://github.com/user-attachments/assets/10e785de-775b-4aff-9021-0508a8313a8d" />

### /set_model
<img width="708" height="479" alt="image" src="https://github.com/user-attachments/assets/8202a4bb-9504-40c4-b769-c75c0236be0b" />
重新取得模型列表並選擇模型。

### /reply

直接輸入對方訊息，
<img width="372" height="57" alt="image" src="https://github.com/user-attachments/assets/bc52de7f-d018-4da0-b8ce-fa3eae6e38e9" />
產生三種建議回答。
<img width="426" height="311" alt="image" src="https://github.com/user-attachments/assets/ec9c6fef-5515-4cbb-a631-4681a668c64c" />


## API 格式

API 必須支援 OpenAI-compatible API：

GET：

/models

POST：

/chat/completions
