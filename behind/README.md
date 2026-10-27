# behind

`behind` 是“心陪陪”项目的 Flask 后端。

当前已经完成：

- Flask 应用工厂与蓝图注册
- SQLAlchemy 数据模型
- 基于 SQLite 的本地开发数据库
- 用户端认证、聊天、状态评估接口
- 管理员端人员、统计、系统设置、人工介入接口
- GLM 对话服务接入入口
- 本地演示数据初始化命令

默认数据库位置：

- `behind/data/app.db`

## 快速开始

```bash
cd behind
pip install -r requirements.txt
flask --app app init-db
flask --app app seed-db
flask --app app run --debug
```

前端本地开发时，`front/vite.config.js` 已经把 `/api` 代理到：

- `http://127.0.0.1:5000`

所以可以直接在 `front` 目录运行：

```bash
npm install
npm run dev
```

## 接入 GLM

后端已经预留 GLM 服务层，配置文件示例见：

- [.env.example](.env.example)

最少需要配置：

```env
GLM_API_KEY=your_glm_api_key
GLM_MODEL=glm-4.7-flash
GLM_BASE_URL=https://api.z.ai/api/paas/v4
OSS_ACCESS_KEY_ID=your_oss_access_key_id
OSS_ACCESS_KEY_SECRET=your_oss_access_key_secret
OSS_BUCKET_NAME=your_bucket_name
OSS_ENDPOINT=https://oss-cn-beijing.aliyuncs.com
OSS_REGION=cn-beijing
OSS_PUBLIC_BASE_URL=
```

如果没配置 `GLM_API_KEY`，聊天接口仍然能工作，但会回退到本地兜底回复逻辑。

## 接入头像上传

注册页头像上传现在走后端转 OSS 的方式，前端点击圆形头像后上传本地 JPG/JPEG 文件。

当前新增接口：

- `POST /api/auth/avatar-upload`

接口使用 `multipart/form-data`，字段名为 `file`，成功后返回可直接展示的 `avatarUrl`。

## 演示账号

- 普通用户
  - 账号：`DEMO_USER_001`
  - 密码：`DEMO_PASSWORD`
- 管理员
  - 账号：`DEMO_ADMIN`
  - 密码：`DEMO_PASSWORD`

## 已实现接口

### 认证

- `POST /api/auth/login`
- `POST /api/auth/admin-login`
- `POST /api/auth/register`
- `POST /api/auth/avatar-upload`
- `POST /api/auth/forgot-password/code`
- `POST /api/auth/forgot-password/reset`

### 用户端

- `GET /api/users/me/profile`
- `GET /api/users/me/settings`
- `PUT /api/users/me/settings`
- `GET /api/conversations`
- `POST /api/conversations`
- `GET /api/conversations/<conversation_id>`
- `GET /api/conversations/<conversation_id>/messages`
- `POST /api/conversations/<conversation_id>/messages`
- `GET /api/assessment/dashboard`
- `GET /api/assessments/latest/<user_id>`

### 管理员端

- `GET /api/admin/users`
- `GET /api/admin/users/<user_id>`
- `PATCH /api/admin/users/<user_id>/prompt`
- `GET /api/admin/business-stats`
- `GET /api/admin/ops-stats`
- `GET /api/admin/system-settings`
- `PUT /api/admin/system-settings`
- `POST /api/admin/interventions`
- `GET /api/admin/interventions/<session_id>`
- `GET /api/admin/interventions/user/<user_id>`
- `POST /api/admin/interventions/<session_id>/messages`
- `POST /api/admin/interventions/<session_id>/finish`

## 说明

- `users.password` 当前仍按你的要求保留明文字段，只适合开发演示。
- `forgot-password` 在开发模式下会直接返回验证码，便于联调前端。
- 运维统计里的接口次数、错误次数、平均响应时间来自进程内运行时指标。
- GLM 当前先接在聊天回复链路上，后续如果你要，我可以继续把评估分析也切到 GLM。

