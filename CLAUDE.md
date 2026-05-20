# Context-Aware Smart Reader

英语学习应用，帮助用户在阅读中识别生词并积累词汇。

## 技术栈

**Backend**: FastAPI + spaCy + Gemini AI (fallback: Free Dictionary API) + PostgreSQL  
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
.venv/bin/pip install "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl"
.venv/bin/uvicorn app.main:app --reload

# Frontend（另开终端）
cd frontend
npm install
npm run dev
```

**backend/.env** 配置：
```
GEMINI_API_KEY=<key>
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
  services/        # 业务逻辑（NLP、翻译、词汇管理）

frontend/src/      # React 组件 + Zustand store + TanStack Query hooks
```

## 已知问题

- Gemini API key 可能过期：若 `translate-word` 始终返回 `is_fallback=true`，需更新 key
- `fastapi-cli` 与 spaCy 存在 typer 版本冲突，无害，用 uvicorn 直接启动即可
- 数据库通过 SQLAlchemy `create_all` 在启动时自动建表，无 Alembic 迁移

## 开发约定

- V1.0 核心功能已完整实现，新工作应聚焦于 bug 修复、体验优化或 Post-MVP 功能
- 后端异步风格（async/await），保持一致
- 前端状态管理：服务端状态用 TanStack Query，客户端 UI 状态用 Zustand
