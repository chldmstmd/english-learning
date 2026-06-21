# 设计文档：译文显隐随主线状态派生 + 「未收录」清理修复

日期：2026-06-21
状态：待实现

## 背景与动机

应用里存在两条相互独立的数据轴：

1. **单词收录状态 `wordStatuses`**（按 `lemma` 词元存）→ 后端 `Vocabulary` 表，状态机为 `new → reviewing → mastered → new`。
2. **位置标注 `ArticleAnnotation`**（按 `文章ID + 句子位置` 存，per-instance）→ 决定某个**点过的位置**头顶是否显示那行红色译文。

点击生词时这两者会同时写入。当前存在一个 bug，且「巩固中」状态形同虚设。本设计一并解决。

## 解决的问题

### 问题 1（bug）：「未收录」只清理了一半数据

在单词库把词改回「未收录」时，只执行 `DELETE /vocab/{word}`，删掉了 `Vocabulary` 行，但该词在各处点过的 `ArticleAnnotation` 标注**原封不动地留在库里**。

回到文章后：
- `word_statuses` 不含此词 → 状态 = `unseen` → 高亮消失；
- `annotations` 里标注仍在 → 当前 `showTranslation = !!annotation?.translation` 为真 → 译文照常显示；
- 点击它（`WordToken.tsx` 当前逻辑：`showTranslation` 为真就走 `openSidebar`）→ 侧边栏请求 `vocab/{lemma}/detail` → 词已删 → 后端 **404** → 侧边栏空白、无操作。

**现象**：译文还在、词却“按不下去”，既不能重新翻译，侧边栏又是空的。

### 问题 2：「巩固中」没有实质意义

`new → reviewing` 没有任何自动晋升逻辑，唯一入口是单词库列表的下拉框；在阅读页里 `new` 和 `reviewing` 行为完全相同（都高亮、点过的位置都显示译文、点击都开侧边栏）；侧边栏也没有进入「巩固中」的按钮。它只是个可筛选的空标签。

同时，用户需要一个「把单词头顶译文隐藏掉」的方法。这两件事可以互相成全。

## 核心设计：译文显隐 = 收录状态的函数

把「单词头顶那行红色译文」理解为**学习脚手架**：越熟，脚手架越少。让它跟主线状态走，用一条与位置无关的统一规则：

> **头顶显示译文 ⟺ 这个位置有标注 且 词的状态是「新词」。**
>
> `showTranslation = !!annotation?.translation && status === "new"`

各状态行为：

| 状态 | 高亮（按词，到处都在） | 头顶译文（仅点过的位置） | 点一个**新位置** | 含义 |
|------|:---:|:---:|------|------|
| 未收录 unseen | 无 | 无 | 翻译 + 收录为「新词」 | 没学过 |
| 新词 new | 琥珀虚线 | **显示** | 译文贴头顶（看答案）| 刚收，看着译文读 |
| 巩固中 reviewing | 琥珀虚线（**与新词相同，不区分**）| **隐藏** | 不贴答案，开侧边栏自测 | 盖住译文靠回忆；点开侧边栏可对答案 |
| 已习得 mastered | 无 | 隐藏 | 开侧边栏 | 学会了 |

### 「巩固中」凭什么和「新词」不同

区别**不在样式**（高亮本次不动，保持一致），而在**点击新位置那一刻会不会给你答案**：

- **新词**：点新位置 → 翻译贴头顶。“给我看答案。”
- **巩固中**：点同样的新位置 → 头顶不贴答案，直接开侧边栏让你先回忆，要对答案再看侧边栏。“逼我自测。”

这个差异在任何位置成立，与 per-instance 的译文是否已存在无关。

### 进入巩固 / 退回新词的落点

侧边栏新增按钮，把这个一直缺失的 `new → reviewing` 入口补上，并补上反向开关，形成可逆 toggle。按钮命名表达**学习动作**（而非"隐藏/显示译文"这种显示效果）——译文随状态派生消失/恢复是动作的自然结果：

- 状态 `new` 时显示 **「进入巩固」**（→ reviewing）：一键把这个词在所有地方从"喂答案"切到"自测"，译文随之收起。
- 状态 `reviewing` 时显示 **「退回新词」**（→ new）：撤销，译文随之恢复。
- 「标记已掌握」（→ mastered）/「重新加入学习」（→ new）按现有逻辑保留。

## 改动清单

### 后端

**1. `annotation_service.py`** — 新增按词删除标注：
```python
async def delete_word_annotations(db, user_id: str, word: str) -> None:
    """删除某用户某词（lemma）在所有文章中的位置标注。调用方负责 commit。"""
    rows = await db.scalars(
        select(ArticleAnnotation).where(
            ArticleAnnotation.user_id == user_id,
            ArticleAnnotation.word == word,
        )
    )
    for ann in rows:
        await db.delete(ann)
```

**2. `routers/vocab.py`** — `delete_vocab` 在删 `Vocabulary` 的同时清理标注：
```python
await vocab_service... # 取到 vocab
await annotation_service.delete_word_annotations(db, current_user.id, word)
await db.delete(vocab)
await db.commit()
```
（`ArticleAnnotation.word` 存的是 lemma，与 `DELETE /vocab/{word}` 的 `word`=lemma 一致，匹配正确。）

### 前端

**3. `WordToken.tsx`** — 译文显隐与点击行为都改为 status 驱动：
- `const showTranslation = !!annotation?.translation && status === "new";`
- 点击行为不再看 `showTranslation`，改看 status：
  ```ts
  if (status === "unseen") {
    translateMutation.mutate();           // 首次：翻译 + 收录
    if (autoOpenSidebar) openSidebar(...);
  } else {
    openSidebar(...);                      // 已收录(new/reviewing/mastered)：开侧边栏管理/自测
  }
  ```
  这是对 bug 的“双保险”：即便有残留标注，unseen 词也能重新翻译。
- `aria-label` 同步用新的 `showTranslation`。

**4. `WordSidebar.tsx`** — 底部操作区按 status 渲染。按钮文案表达「学习动作」而非「显示效果」——译文消失/恢复是状态切换的自然结果，不单独命名：
- `new`：`[进入巩固 → reviewing]` `[标记已掌握 → mastered]`
- `reviewing`：`[退回新词 → new]` `[标记已掌握 → mastered]`
- `mastered`：`[重新加入学习 → new]`

复用现有 `statusMutation`（已带 `force=true`，可任意流转），成功后 `setWordStatus` + 失效 `vocab` / `vocab-detail` 查询。

## 数据流与一致性

- **未收录后回到文章（双层保障）**：
  - 第一层（即时显示）：未收录把状态置为 `unseen`，`WordToken` 的 `showTranslation = !!annotation?.translation && status === "new"` 立即判否 —— 即便内存里还残留该位置标注，译文也不会显示，且点击走 `status==="unseen"` 分支可重新翻译。这是显示正确性的根本保障，不依赖任何刷新。
  - 第二层（数据清理）：后端删除该 lemma 的所有 `ArticleAnnotation`；前端在未收录的 `onSuccess` 里 **主动失效** `["article"]` / `["library-article"]` 查询，迫使文章重新拉取，`initFromArticle` 重新 seed store 时被删标注不再返回。
  - 注意：全局 `staleTime: 30_000`（见 `main.tsx`），若不主动失效，30s 内回到文章不会自动刷新 —— 因此第二层显式 invalidate 是必需的，不能依赖“挂载即刷新”。`wordStatuses` 用合并，本地遗留的 `unseen` 条目无害（`getStatus` 本就回落 unseen）。前端无法按 lemma 清理内存标注（标注按位置存、不带 lemma），故依赖后端删除 + 主动失效刷新。
- **进入巩固 / 退回新词**：`statusMutation` 成功后 `setWordStatus(lemma, ...)` 立即更新 store，`WordToken` 经 `getStatus` 重渲染，头顶译文随 `showTranslation` 公式立即显隐，无需刷新文章。

## 明确的取舍（YAGNI）

- **巩固中的高亮不做区分**：本次不引入弱化样式，新词与巩固中视觉一致。区别完全由“点新位置给不给答案”体现。（高亮样式可作为后续独立优化。）
- **巩固中点新位置不记录 location、不发翻译请求**：直接开侧边栏自测，保持点击逻辑单纯由 status 分叉。`你点过的位置` 列表只收集新词点击（用户主动学习时的位置），足够有用，避免每次自测点击都打后端。

## 测试要点

1. **bug 修复**：点词→收录→单词库改「未收录」→回文章：译文消失、高亮消失、可重新点击翻译并重新收录；删词后该 lemma 的 `ArticleAnnotation` 全部清空。
2. **进入巩固 / 退回新词**：新词点开侧边栏→「进入巩固」→词变 reviewing、头顶译文消失、高亮仍在；再点该词开侧边栏出现「退回新词」→点击→词变回 new、译文恢复。
3. **巩固中点新位置**：reviewing 词在未点过的位置点击→不贴译文、直接开侧边栏；new 词在新位置点击→译文贴头顶。
4. **已习得**：mastered 词无高亮、无译文，点击开侧边栏，可「重新加入学习」。
