# 心陪陪 · 情感陪护虚拟数字人系统(Vibe Coding)

系统面向青年情感陪伴场景，包含文本聊天、语音/视频输入入口、状态评估、用户画像、对话式量表、管理后台与人工介入。前端提供 Live2D 渲染适配，后端可接入大语言模型、语音识别/合成与知识库检索。

## 保留范围

- `front/`：Vue 3、Vite、Pinia、Vue Router、Socket.IO 客户端与数字人交互源码。
- `behind/`：Flask、SQLAlchemy、Socket.IO、模型调用适配、认证、聊天、评估和管理接口。
- `behind/data/profile_template.json`、`questionnaire_items.json`：画像字段和问卷定义，不含用户业务数据。
- Dockerfile、依赖清单与前端依赖锁文件。

## 未保留的内容

以下资源需按实际部署环境另行准备：

- 数字人反应生成模块 `live2d_service/` 及其依赖和模型权重。
- SenseVoice 等语音模型及本地模型缓存。
- Live2D Haru/Hiyori 模型、纹理、动作及 Cubism SDK 和本地 vendor 运行资源。
- 用户数据库、聊天记录、上传的音视频、语音合成结果、用户画像实例、运行日志及知识库索引。
- 实际 `.env`、API 密钥、OSS 配置、依赖目录和构建产物。

## 本地启动

需要 Python 3.10+、Node.js 20+。以下为 PowerShell 命令，均从仓库根目录执行。

后端：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r behind/requirements.txt
Copy-Item behind/.env.example behind/.env
$env:CHAT_REQUIRE_GLM = "0"
$env:ASR_BACKEND = "demo"
$env:TTS_BACKEND = "demo"
python -m flask --app behind.app:create_app seed-db
python -m flask --app behind.app:create_app run --port 5000
```

应用工厂会创建 SQLite 数据表；`seed-db` 用于生成本地演示数据。默认数据库为 `behind/data/app.db`。

前端在另一个终端启动：

```powershell
cd front
npm ci
npm run dev
```

访问 `http://localhost:5173`；Vite 将 `/api`、`/static` 和 `/socket.io` 代理到 `http://127.0.0.1:5000`。

前端构建：`cd front; npm run build`。

## 配置与能力边界

- 真实聊天：在 `behind/.env` 配置 `LLM_PROVIDER` 以及对应的 API Key、模型名和服务地址；支持 GLM、Qwen、DeepSeek 和兼容接口。未配置时，上述 `CHAT_REQUIRE_GLM=0` 用于本地兜底文本回复。
- 头像上传：需自行配置 OSS 凭据、Bucket 和 Endpoint。
- 语音：默认 demo 配置不代表真实语音识别/合成能力；真实能力需要另行配置后端、依赖和模型或云服务凭据。使用本地 ASR 时，将 `ASR_RUNTIME_PYTHON` 设置为实际 Python 解释器路径，替换默认占位符。
- 数字人显示：需要自行合法获取并恢复 `front/public/live2d/`、`front/public/live2d-sdk/` 和 `front/public/vendor/` 下的对应资源；模型路径见 `front/src/config/live2dModels.js`，运行库路径见 `front/src/utils/haruLive2dPlayer.js`。
- 视频/多模态推理：需要另外提供 `live2d_service` 代码、依赖与模型权重，仅补权重不足以运行。默认 checkpoint 路径见 `behind/config.py`，可通过 `DIGITAL_HUMAN_CHECKPOINT_PATH` 覆盖。
- RAG：需要自行提供知识源并重建索引；原知识库及索引不在本仓库。

后端默认端口为 5000，前端开发端口为 5173。Dockerfile 作为原实现保留；仓库未提供完整模型资源或完整部署环境。

## 原型实现说明

当前认证代码仍保留明文密码存储、开发用固定签名密钥及演示账号，适合本地阅读和演示；如需上线，应先改为密码哈希、从环境读取独立密钥，并关闭验证码回传等调试行为。心理状态结果属于系统演示输出，不作为临床诊断。

子目录 README 可能描述旧版接口，以实际代码及本说明为准。
