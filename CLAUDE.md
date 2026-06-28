# Context Translation Layer

语境翻译服务原型。当前重点是浏览器插件可复用的实时翻译与预翻译 API；Web UI 只保留最小测试壳。

## 技术栈

**Backend**: FastAPI + spaCy + DeepSeek AI + optional free translation fallback + PostgreSQL  
**Frontend**: React + Zustand + TanStack Query + Tailwind CSS  
**Infrastructure**: Docker Compose (PostgreSQL)

## 本地运行

```bash
# 启动数据库（首次或重启后）
docker compose up -d

# Backend
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload

# Frontend（另开终端）
cd frontend
npm install
npm run dev
```

**backend/.env** 配置：
```
DEEPSEEK_API_KEY=<key>
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/english_learning
```

## 项目结构

```
backend/app/
  main.py          # FastAPI 入口，startup 时 create_all 建表
  config.py        # 环境变量配置
  database.py      # 异步 SQLAlchemy 会话
  models/          # ORM 模型
  routers/         # API 路由
  schemas/         # Pydantic 模型
  services/        # 业务逻辑（NLP、翻译、最小用户状态）

frontend/src/      # 最小 React 测试壳 + Zustand store + TanStack Query hooks
```

## 已知问题

- spaCy 模型 `en_core_web_sm` 可选；缺失时会降级到基础英文 tokenizer
- DeepSeek API key 可能过期：若 `translate-word` 返回 503 或 fallback 结果，需更新 key
- `fastapi-cli` 与 spaCy 存在 typer 版本冲突，无害，用 uvicorn 直接启动即可
- 数据库通过 SQLAlchemy `create_all` 在启动时自动建表，无 Alembic 迁移

## 开发约定

- 新工作优先围绕浏览器插件、翻译引擎、预翻译缓存和订阅化服务
- 后端异步风格（async/await），保持一致
- 前端状态管理：服务端状态用 TanStack Query，客户端 UI 状态用 Zustand
