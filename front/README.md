# 青年人心理陪伴数字人系统前端模板

基于 Vue 3 + Vite + Pinia + Vue Router + axios 的前后端分离前端骨架，面向“青年人心理陪伴数字人系统”场景，内置聊天演示流程、媒体采集、情绪状态卡片、WebSocket 基础封装、Live2D SDK 预留层与 mock 数据回退。

## 启动方式

```bash
npm install
npm run dev
```

默认地址：

- 开发环境：`http://localhost:5173`
- 预设后端：`http://127.0.0.1:5000`

## 构建命令

```bash
npm run build
npm run preview
```

## 目录结构

```text
front
├─ public
│  └─ favicon.svg
├─ src
│  ├─ api
│  │  ├─ dialogueApi.js
│  │  ├─ http.js
│  │  └─ sessionApi.js
│  ├─ components
│  │  ├─ AppHeader.vue
│  │  ├─ AvatarPanel.vue
│  │  ├─ CameraPreview.vue
│  │  ├─ ChatInput.vue
│  │  ├─ ChatMessageList.vue
│  │  ├─ ChatPanel.vue
│  │  ├─ EmotionCard.vue
│  │  ├─ LoadingOverlay.vue
│  │  ├─ RecorderButton.vue
│  │  ├─ RiskBadge.vue
│  │  └─ SidebarNav.vue
│  ├─ composables
│  │  ├─ useCamera.js
│  │  └─ useRecorder.js
│  ├─ config
│  │  └─ index.js
│  ├─ mocks
│  │  └─ dialogueMock.js
│  ├─ router
│  │  └─ index.js
│  ├─ store
│  │  ├─ avatar.js
│  │  ├─ chat.js
│  │  ├─ emotion.js
│  │  └─ session.js
│  ├─ utils
│  │  ├─ audioPlayer.js
│  │  ├─ live2dAdapter.js
│  │  └─ websocket.js
│  ├─ views
│  │  ├─ ChatView.vue
│  │  ├─ HistoryView.vue
│  │  ├─ HomeView.vue
│  │  └─ SettingsView.vue
│  ├─ App.vue
│  ├─ main.js
│  └─ style.css
├─ index.html
├─ jsconfig.json
├─ package.json
└─ vite.config.js
```

## Mock 模式切换

统一配置位于 `src/config/index.js`：

- `API_BASE_URL`
- `WS_BASE_URL`
- `ENABLE_MOCK`

默认关闭 mock 模式，优先走真实后端。你也可以通过 Vite 环境变量覆盖：

```bash
VITE_API_BASE_URL=http://127.0.0.1:5000
VITE_WS_BASE_URL=ws://127.0.0.1:5000/ws
VITE_ENABLE_MOCK=false
```

当 `ENABLE_MOCK=false` 时，前端会严格请求真实后端；如果后端不可用或接口报错，页面会直接显示错误，不再自动回退到 mock 数据。

## 主业务流程

`ChatView.vue` 内置演示流程：

1. 页面加载时自动创建会话。
2. 用户发送文本后，先写入本地消息列表。
3. 调用 `processDialogue()` 发送 `session_id`、文本、音频占位和视频帧占位。
4. 根据返回值更新：
   - 聊天消息
   - 情绪识别结果
   - 风险等级
   - 数字人动作参数
   - TTS 音频播放

## Live2D 接入说明

当前项目已预留 Live2D 适配层：

- 组件入口：`src/components/AvatarPanel.vue`
- 适配器：`src/utils/live2dAdapter.js`

后续接入 SDK 时，建议按以下顺序扩展：

1. 在 `initLive2D()` 中初始化渲染上下文。
2. 在 `loadModel()` 中加载模型资源。
3. 在 `setExpression()`、`playMotion()`、`syncLip()` 中接入具体 SDK API。
4. 继续通过 `avatar store` 驱动 `AvatarPanel`，避免把渲染细节散落在业务页面里。

## Flask 后端接口约定

- `POST /api/session/create`
- `POST /api/dialogue/process`
- `GET /api/session/history`（前端先作为历史记录占位接口）

## 媒体能力说明

- `useCamera.js`：摄像头预览和 `captureFrame()` 能力。
- `useRecorder.js`：麦克风录音和音频 Blob 回调。
- `audioPlayer.js`：TTS 音频播放工具。
- `websocket.js`：WebSocket 连接、发送、监听、断开基础封装。

## 后续建议

- 接入 Flask 返回的真实 ASR/TTS/情绪识别结果。
- 在 `HistoryView.vue` 中补充会话回放与筛选。
- 将 `avatar_action` 与 Live2D SDK 事件映射起来。
- 视后端能力升级 `processDialogue()` 为 multipart 或流式接口。
