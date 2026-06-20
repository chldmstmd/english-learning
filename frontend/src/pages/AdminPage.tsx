import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Pencil, Trash2, X } from "lucide-react";
import { api } from "../api/client";
import { PageNav } from "../components/PageNav";
import type { LibraryArticleListItem, LibraryBookListItem } from "../types";

const CATEGORIES = [
  { value: "", label: "无分类" },
  { value: "science-technology", label: "科技" },
  { value: "health-lifestyle", label: "健康" },
  { value: "us-history", label: "美国历史" },
  { value: "words-stories", label: "词汇故事" },
];

const DIFFICULTIES = [
  { value: "", label: "无难度" },
  { value: "level1", label: "Level 1 · 慢速" },
  { value: "level2", label: "Level 2 · 标准" },
];

function DifficultyBadge({ difficulty }: { difficulty: string | null | undefined }) {
  if (!difficulty) return null;
  return (
    <span className={`inline-block text-xs px-1.5 py-0.5 rounded font-medium ${
      difficulty === "level1" ? "bg-green-100 text-green-700" : "bg-blue-100 text-blue-700"
    }`}>
      {difficulty === "level1" ? "L1" : "L2"}
    </span>
  );
}

type ArticleFormState = {
  mode: "create" | "edit";
  editId: string | null;
  title: string;
  raw_text: string;
  difficulty: string;
  source_category: string;
};

const EMPTY_ARTICLE_FORM: ArticleFormState = {
  mode: "create",
  editId: null,
  title: "",
  raw_text: "",
  difficulty: "",
  source_category: "",
};

function ArticlesTab() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ArticleFormState>(EMPTY_ARTICLE_FORM);
  const [formError, setFormError] = useState("");

  const { data: articles, isLoading } = useQuery({
    queryKey: ["library", "", "", 1],
    queryFn: () => api.get("library?page_size=100").json<LibraryArticleListItem[]>(),
  });

  const createMutation = useMutation({
    mutationFn: (body: object) => api.post("admin/library/articles", { json: body }).json(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["library"] });
      setForm(EMPTY_ARTICLE_FORM);
      setFormError("");
    },
    onError: async (err: any) => {
      const msg = await err.response?.json().catch(() => null);
      setFormError(msg?.detail ?? "创建失败");
    },
  });

  const editMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: object }) =>
      api.patch(`admin/library/articles/${id}`, { json: body }).json(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["library"] });
      setForm(EMPTY_ARTICLE_FORM);
      setFormError("");
    },
    onError: async (err: any) => {
      const msg = await err.response?.json().catch(() => null);
      setFormError(msg?.detail ?? "更新失败");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`admin/library/articles/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["library"] }),
  });

  function handleEdit(article: LibraryArticleListItem) {
    setForm({
      mode: "edit",
      editId: article.id,
      title: article.title,
      raw_text: "",
      difficulty: article.difficulty ?? "",
      source_category: article.source_category ?? "",
    });
    setFormError("");
  }

  function handleDelete(article: LibraryArticleListItem) {
    if (window.confirm(`确认删除「${article.title}」？此操作不可撤销。`)) {
      deleteMutation.mutate(article.id);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError("");
    if (form.mode === "create") {
      createMutation.mutate({
        title: form.title,
        raw_text: form.raw_text,
        difficulty: form.difficulty || null,
        source_category: form.source_category || null,
      });
    } else if (form.editId) {
      editMutation.mutate({
        id: form.editId,
        body: {
          title: form.title,
          difficulty: form.difficulty || null,
          source_category: form.source_category || null,
        },
      });
    }
  }

  const isSaving = createMutation.isPending || editMutation.isPending;

  return (
    <div className="flex gap-6 mt-6">
      {/* Left: article list */}
      <div className="w-1/2 overflow-y-auto max-h-[70vh] border border-gray-100 rounded-xl">
        {isLoading && <p className="text-sm text-gray-400 p-4">加载中...</p>}
        {!isLoading && (!articles || articles.length === 0) && (
          <p className="text-sm text-gray-400 p-4">暂无文章</p>
        )}
        {articles?.map((a) => (
          <div key={a.id} className="flex items-start justify-between p-3 border-b border-gray-50 last:border-0 hover:bg-gray-50">
            <div className="flex-1 min-w-0 mr-2">
              <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                <DifficultyBadge difficulty={a.difficulty} />
                {a.source_category && (
                  <span className="text-xs text-gray-400">
                    {CATEGORIES.find((c) => c.value === a.source_category)?.label ?? a.source_category}
                  </span>
                )}
              </div>
              <p className="text-sm font-medium text-gray-800 line-clamp-1">{a.title}</p>
              <p className="text-xs text-gray-400 mt-0.5">{a.word_count.toLocaleString()} 词</p>
            </div>
            <div className="flex gap-1 shrink-0">
              <button
                onClick={() => handleEdit(a)}
                className="p-1.5 text-gray-400 hover:text-blue-500 transition-colors"
                title="编辑"
              >
                <Pencil size={14} />
              </button>
              <button
                onClick={() => handleDelete(a)}
                className="p-1.5 text-gray-400 hover:text-red-500 transition-colors"
                title="删除"
              >
                <Trash2 size={14} />
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Right: create/edit form */}
      <div className="w-1/2">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-gray-700">
            {form.mode === "create" ? "新建文章" : "编辑文章"}
          </h2>
          {form.mode === "edit" && (
            <button onClick={() => setForm(EMPTY_ARTICLE_FORM)} className="text-gray-400 hover:text-gray-600">
              <X size={16} />
            </button>
          )}
        </div>
        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            type="text"
            placeholder="标题"
            value={form.title}
            onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            required
            className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          {form.mode === "create" && (
            <textarea
              placeholder="正文（纯英文文本）"
              value={form.raw_text}
              onChange={(e) => setForm((f) => ({ ...f, raw_text: e.target.value }))}
              required
              rows={12}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400 resize-y font-mono"
            />
          )}
          <select
            value={form.difficulty}
            onChange={(e) => setForm((f) => ({ ...f, difficulty: e.target.value }))}
            className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
          >
            {DIFFICULTIES.map((d) => (
              <option key={d.value} value={d.value}>{d.label}</option>
            ))}
          </select>
          <select
            value={form.source_category}
            onChange={(e) => setForm((f) => ({ ...f, source_category: e.target.value }))}
            className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
          >
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
          {formError && <p className="text-xs text-red-500">{formError}</p>}
          <button
            type="submit"
            disabled={isSaving}
            className="w-full py-2 bg-blue-500 text-white text-sm font-medium rounded-lg hover:bg-blue-600 disabled:opacity-50 transition-colors"
          >
            {isSaving ? "保存中..." : form.mode === "create" ? "创建文章" : "保存修改"}
          </button>
        </form>
      </div>
    </div>
  );
}

function BookChapterList({
  bookId,
  onDeleteChapter,
}: {
  bookId: string;
  onDeleteChapter: (bookId: string, chapterId: string, title: string) => void;
}) {
  const { data: bookDetail, isLoading } = useQuery({
    queryKey: ["library-book-detail", bookId],
    queryFn: () => api.get(`library/books/${bookId}`).json<{ chapters: { id: string; title: string; chapter_order: number; word_count: number }[] }>(),
  });

  if (isLoading) return <p className="text-xs text-gray-400 px-8 pb-2">加载章节...</p>;
  if (!bookDetail?.chapters?.length) return <p className="text-xs text-gray-400 px-8 pb-2">暂无章节</p>;

  return (
    <div className="bg-gray-50 px-8 pb-2">
      {bookDetail.chapters.map((ch) => (
        <div key={ch.id} className="flex items-center justify-between py-1.5 border-b border-gray-100 last:border-0">
          <div>
            <span className="text-xs text-gray-500 mr-2">Ch.{ch.chapter_order}</span>
            <span className="text-xs text-gray-700">{ch.title}</span>
            <span className="text-xs text-gray-400 ml-2">{ch.word_count.toLocaleString()} 词</span>
          </div>
          <button
            onClick={() => onDeleteChapter(bookId, ch.id, ch.title)}
            className="p-1 text-gray-300 hover:text-red-500 transition-colors"
            title="删除章节"
          >
            <Trash2 size={12} />
          </button>
        </div>
      ))}
    </div>
  );
}

type BookFormState = {
  title: string;
  cover_image_url: string;
  source_category: string;
};

const EMPTY_BOOK_FORM: BookFormState = { title: "", cover_image_url: "", source_category: "" };

type ChapterFormState = {
  book_id: string;
  title: string;
  raw_text: string;
};

const EMPTY_CHAPTER_FORM: ChapterFormState = { book_id: "", title: "", raw_text: "" };

function BooksTab() {
  const queryClient = useQueryClient();
  const [expandedBookId, setExpandedBookId] = useState<string | null>(null);
  const [bookForm, setBookForm] = useState<BookFormState>(EMPTY_BOOK_FORM);
  const [bookFormError, setBookFormError] = useState("");
  const [chapterForm, setChapterForm] = useState<ChapterFormState>(EMPTY_CHAPTER_FORM);
  const [chapterFormError, setChapterFormError] = useState("");

  const { data: books, isLoading } = useQuery({
    queryKey: ["library-books"],
    queryFn: () => api.get("library/books").json<LibraryBookListItem[]>(),
  });

  const createBookMutation = useMutation({
    mutationFn: (body: object) => api.post("admin/library/books", { json: body }).json(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["library-books"] });
      setBookForm(EMPTY_BOOK_FORM);
      setBookFormError("");
    },
    onError: async (err: any) => {
      const msg = await err.response?.json().catch(() => null);
      setBookFormError(msg?.detail ?? "创建失败");
    },
  });

  const deleteBookMutation = useMutation({
    mutationFn: (id: string) => api.delete(`admin/library/books/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["library-books"] }),
  });

  const addChapterMutation = useMutation({
    mutationFn: ({ bookId, body }: { bookId: string; body: object }) =>
      api.post(`admin/library/books/${bookId}/chapters`, { json: body }).json(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["library-books"] });
      setChapterForm(EMPTY_CHAPTER_FORM);
      setChapterFormError("");
    },
    onError: async (err: any) => {
      const msg = await err.response?.json().catch(() => null);
      setChapterFormError(msg?.detail ?? "添加失败");
    },
  });

  const deleteChapterMutation = useMutation({
    mutationFn: ({ bookId, chapterId }: { bookId: string; chapterId: string }) =>
      api.delete(`admin/library/books/${bookId}/chapters/${chapterId}`),
    onSuccess: (_, { bookId }) => {
      queryClient.invalidateQueries({ queryKey: ["library-books"] });
      queryClient.invalidateQueries({ queryKey: ["library-book-detail", bookId] });
    },
  });

  function handleDeleteBook(book: LibraryBookListItem) {
    if (window.confirm(`确认删除图书「${book.title}」及其所有章节？此操作不可撤销。`)) {
      deleteBookMutation.mutate(book.id);
    }
  }

  function handleDeleteChapter(bookId: string, chapterId: string, chapterTitle: string) {
    if (window.confirm(`确认删除章节「${chapterTitle}」？`)) {
      deleteChapterMutation.mutate({ bookId, chapterId });
    }
  }

  function handleBookSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBookFormError("");
    createBookMutation.mutate({
      title: bookForm.title,
      cover_image_url: bookForm.cover_image_url || null,
      source_category: bookForm.source_category || null,
    });
  }

  function handleChapterSubmit(e: React.FormEvent) {
    e.preventDefault();
    setChapterFormError("");
    if (!chapterForm.book_id) {
      setChapterFormError("请选择图书");
      return;
    }
    addChapterMutation.mutate({
      bookId: chapterForm.book_id,
      body: { title: chapterForm.title, raw_text: chapterForm.raw_text },
    });
  }

  return (
    <div className="flex gap-6 mt-6">
      {/* Left: book list */}
      <div className="w-1/2 overflow-y-auto max-h-[70vh] border border-gray-100 rounded-xl">
        {isLoading && <p className="text-sm text-gray-400 p-4">加载中...</p>}
        {!isLoading && (!books || books.length === 0) && (
          <p className="text-sm text-gray-400 p-4">暂无图书</p>
        )}
        {books?.map((book) => (
          <div key={book.id} className="border-b border-gray-50 last:border-0">
            <div
              className="flex items-center justify-between p-3 hover:bg-gray-50 cursor-pointer"
              onClick={() => setExpandedBookId(expandedBookId === book.id ? null : book.id)}
            >
              <div className="flex items-center gap-2 flex-1 min-w-0">
                {expandedBookId === book.id ? <ChevronDown size={14} className="text-gray-400 shrink-0" /> : <ChevronRight size={14} className="text-gray-400 shrink-0" />}
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-800 line-clamp-1">{book.title}</p>
                  <p className="text-xs text-gray-400">{book.chapter_count} 章</p>
                </div>
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); handleDeleteBook(book); }}
                className="p-1.5 text-gray-400 hover:text-red-500 transition-colors shrink-0"
                title="删除图书"
              >
                <Trash2 size={14} />
              </button>
            </div>
            {expandedBookId === book.id && (
              <BookChapterList bookId={book.id} onDeleteChapter={handleDeleteChapter} />
            )}
          </div>
        ))}
      </div>

      {/* Right: forms */}
      <div className="w-1/2 space-y-6">
        {/* Create book form */}
        <div>
          <h2 className="text-sm font-semibold text-gray-700 mb-3">新建图书</h2>
          <form onSubmit={handleBookSubmit} className="space-y-3">
            <input
              type="text"
              placeholder="书名"
              value={bookForm.title}
              onChange={(e) => setBookForm((f) => ({ ...f, title: e.target.value }))}
              required
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
            <input
              type="url"
              placeholder="封面图片 URL（选填）"
              value={bookForm.cover_image_url}
              onChange={(e) => setBookForm((f) => ({ ...f, cover_image_url: e.target.value }))}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
            <select
              value={bookForm.source_category}
              onChange={(e) => setBookForm((f) => ({ ...f, source_category: e.target.value }))}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
            >
              {CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
            {bookFormError && <p className="text-xs text-red-500">{bookFormError}</p>}
            <button
              type="submit"
              disabled={createBookMutation.isPending}
              className="w-full py-2 bg-blue-500 text-white text-sm font-medium rounded-lg hover:bg-blue-600 disabled:opacity-50 transition-colors"
            >
              {createBookMutation.isPending ? "创建中..." : "创建图书"}
            </button>
          </form>
        </div>

        <div className="border-t border-gray-100 pt-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">添加章节</h2>
          <form onSubmit={handleChapterSubmit} className="space-y-3">
            <select
              value={chapterForm.book_id}
              onChange={(e) => setChapterForm((f) => ({ ...f, book_id: e.target.value }))}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
            >
              <option value="">选择图书</option>
              {books?.map((b) => (
                <option key={b.id} value={b.id}>{b.title}</option>
              ))}
            </select>
            <input
              type="text"
              placeholder="章节标题"
              value={chapterForm.title}
              onChange={(e) => setChapterForm((f) => ({ ...f, title: e.target.value }))}
              required
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
            <textarea
              placeholder="章节正文（纯英文文本）"
              value={chapterForm.raw_text}
              onChange={(e) => setChapterForm((f) => ({ ...f, raw_text: e.target.value }))}
              required
              rows={10}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400 resize-y font-mono"
            />
            {chapterFormError && <p className="text-xs text-red-500">{chapterFormError}</p>}
            <button
              type="submit"
              disabled={addChapterMutation.isPending}
              className="w-full py-2 bg-blue-500 text-white text-sm font-medium rounded-lg hover:bg-blue-600 disabled:opacity-50 transition-colors"
            >
              {addChapterMutation.isPending ? "添加中..." : "添加章节"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

export default function AdminPage() {
  const [tab, setTab] = useState<"articles" | "books">("articles");

  return (
    <div className="min-h-screen bg-white">
      <PageNav />
      <div className="max-w-5xl mx-auto px-6 py-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">内容管理</h1>

        <div className="flex gap-1 border-b border-gray-100 mb-0">
          <button
            onClick={() => setTab("articles")}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              tab === "articles" ? "border-blue-500 text-blue-600" : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            文章
          </button>
          <button
            onClick={() => setTab("books")}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              tab === "books" ? "border-blue-500 text-blue-600" : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            图书
          </button>
        </div>

        {tab === "articles" && <ArticlesTab />}
        {tab === "books" && <BooksTab />}
      </div>
    </div>
  );
}
