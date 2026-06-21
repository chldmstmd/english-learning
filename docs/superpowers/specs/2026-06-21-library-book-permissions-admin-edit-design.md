# 公共库图书权限 + 管理员编辑图书 — 设计

日期：2026-06-21

## 背景

两个 bug：

1. **普通用户在已收藏的公共库图书上看到「+ 添加章节」按钮，但无权添加。**
   `/books/:id`（`BookDetailPage`）同时服务于用户自有图书和已保存到书架的公共库图书。该页无条件渲染「+ 添加章节」按钮。但后端 `POST /books/{id}/chapters`（`books.py`）要求 `Book.user_id == current_user.id`，对公共库图书（归属管理员）会返回 404。UI 暴露了一个无法成功的操作。

2. **管理员无法编辑图书本身。**
   `AdminPage` → `BooksTab` 支持创建图书、编辑/删除/翻译章节、删除图书，但没有编辑图书自身字段（书名/封面/分类）的入口，后端也没有对应的 `PATCH /admin/library/books/{id}` 端点。

## Bug 1 — 在已收藏的公共库图书上隐藏「+ 添加章节」

通过暴露归属信息，让前端能区分自有图书与公共库图书。

### 后端
- `schemas/book.py`：在 `BookDetailResponse` 增加 `is_owner: bool`。
- `books.py` 的 `get_book`：设置 `is_owner = (book.user_id == current_user.id)`。
  - 对已保存的公共库图书，归属是管理员，因此对保存它的普通用户来说 `is_owner == False`。

### 前端
- `BookDetailPage`：仅当 `book.is_owner` 为真时，才渲染「章节目录」标题旁的 `+ 添加章节` 按钮及其展开的添加表单。
- 类型：在 `BookDetail`（`types.ts`）增加 `is_owner: boolean`。
- 不加徽章、不加只读提示，其余 UI 不变（用户已确认「只隐藏按钮」）。

## Bug 2 — 管理员可编辑图书自身字段

为图书新增编辑能力，可编辑字段为**书名 + 封面 URL + 分类**（与「新建图书」表单一致）。这是纯元数据编辑，不触碰章节、token 或翻译。

### 后端
- `schemas/book.py`：新增 `BookPatchRequest`，所有字段可选：
  - `title: str | None = None`
  - `cover_image_url: str | None = None`
  - `source_category: str | None = None`
- `admin.py`：新增 `PATCH /admin/library/books/{book_id}`，由 `require_content_admin` 守护：
  - 查 `Book.id == book_id AND Book.is_library == True`；不存在则 404。
  - 仅对「显式提供（不为 None）」的字段赋值。
  - `await db.commit()`，返回 `LibraryBookListItem`（与 create 端点一致；`chapter_count` 按需填充）。

### 前端（`AdminPage` → `BooksTab`）
- 将现有「新建图书」表单改为**双模式（create/edit）**，参照 `ArticlesTab` 已有的做法：
  - 引入 `BookFormState` 增加 `mode: "create" | "edit"` 与 `editId: string | null`。
  - 标题随模式切换为「新建图书」/「编辑图书」；编辑模式下显示 X 按钮，点击取消回到 create 模式（清空表单）。
  - 提交按钮文案随模式切换为「创建图书」/「保存修改」。
- 在每个图书行的删除按钮旁加一个 Pencil 编辑按钮：点击 `e.stopPropagation()`（避免触发展开/收起），将该书的 `title / cover_image_url / source_category` 载入表单并切到 edit 模式。
- 新增 `editBookMutation`：`PATCH admin/library/books/{id}`，成功后 invalidate `["library-books"]` 并重置表单回 create 模式。

## 范围之外（YAGNI）

- 公共库图书的只读徽章/提示（已确认只隐藏按钮）。
- `ArticleListPage` 中自有图书的编辑（不改动）。
- 章节、翻译、标注相关逻辑（不改动）。

## 测试

- 后端：为 `PATCH /admin/library/books/{id}` 增加测试——成功部分更新、404（不存在或非 library 图书）、非管理员 403。复用现有 `tests/test_library_books.py` 的测试基础设施。
- 前端/手动：
  - 普通用户保存一本公共库书 → 打开 `/books/:id` → 不出现「+ 添加章节」。
  - 自有书 → 打开 `/books/:id` → 仍出现「+ 添加章节」且可用。
  - 管理员在内容管理→图书，点击编辑图书 → 改书名/封面/分类 → 保存 → 列表刷新反映改动。
