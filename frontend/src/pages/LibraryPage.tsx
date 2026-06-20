import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Bookmark, BookmarkCheck } from "lucide-react";
import { api } from "../api/client";
import { PageNav } from "../components/PageNav";
import type { LibraryArticleListItem, LibraryBookListItem, Difficulty } from "../types";

const CATEGORIES = [
  { value: "", label: "全部话题" },
  { value: "science-technology", label: "科技" },
  { value: "health-lifestyle", label: "健康" },
  { value: "us-history", label: "美国历史" },
  { value: "words-stories", label: "词汇故事" },
];

const DIFFICULTIES = [
  { value: "", label: "全部难度" },
  { value: "level1", label: "Level 1 · 慢速" },
  { value: "level2", label: "Level 2 · 标准" },
];

function DifficultyBadge({ difficulty }: { difficulty: Difficulty | null }) {
  if (!difficulty) return null;
  const isLevel1 = difficulty === "level1";
  return (
    <span
      className={`inline-block text-xs px-1.5 py-0.5 rounded font-medium ${
        isLevel1 ? "bg-green-100 text-green-700" : "bg-blue-100 text-blue-700"
      }`}
    >
      {isLevel1 ? "L1" : "L2"}
    </span>
  );
}

function estimateReadTime(wordCount: number): string {
  const minutes = Math.ceil(wordCount / 200);
  return `${minutes} 分钟`;
}

function ArticleCard({
  article,
  onBookmark,
}: {
  article: LibraryArticleListItem;
  onBookmark: (id: string, bookmarked: boolean) => void;
}) {
  return (
    <div className="relative group">
      <Link
        to={`/library/${article.id}`}
        className="block bg-white border border-gray-200 rounded-xl overflow-hidden hover:shadow-md transition-shadow"
      >
        {article.cover_image_url && (
          <div className="h-36 overflow-hidden bg-gray-100">
            <img
              src={article.cover_image_url}
              alt=""
              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
              loading="lazy"
            />
          </div>
        )}
        <div className="p-4">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <DifficultyBadge difficulty={article.difficulty} />
            {article.source_category && (
              <span className="text-xs text-gray-400">
                {CATEGORIES.find((c) => c.value === article.source_category)?.label ??
                  article.source_category}
              </span>
            )}
            {article.read_at && (
              <span className="text-xs text-gray-300 ml-auto">已读</span>
            )}
          </div>
          <h3
            className={`font-medium text-sm leading-snug line-clamp-2 group-hover:text-blue-600 transition-colors ${
              article.read_at ? "text-gray-500" : "text-gray-800"
            }`}
          >
            {article.title}
          </h3>
          <div className="flex items-center gap-2 mt-2 text-xs text-gray-400">
            <span>{article.word_count.toLocaleString()} 词</span>
            <span>·</span>
            <span>{estimateReadTime(article.word_count)}</span>
            {article.published_at && (
              <>
                <span>·</span>
                <span>{new Date(article.published_at).toLocaleDateString("zh-CN")}</span>
              </>
            )}
          </div>
        </div>
      </Link>
      <button
        onClick={(e) => {
          e.preventDefault();
          onBookmark(article.id, !article.is_bookmarked);
        }}
        className={`absolute top-2 right-2 p-1.5 rounded-full transition-all ${
          article.is_bookmarked
            ? "bg-blue-50 text-blue-500"
            : "bg-white/80 text-gray-300 hover:text-blue-400 opacity-0 group-hover:opacity-100"
        } shadow-sm`}
        aria-label={article.is_bookmarked ? "取消收藏" : "收藏"}
        title={article.is_bookmarked ? "取消收藏" : "收藏"}
      >
        {article.is_bookmarked ? <BookmarkCheck size={15} /> : <Bookmark size={15} />}
      </button>
    </div>
  );
}

function BookCard({
  book,
  onSave,
}: {
  book: LibraryBookListItem;
  onSave: (id: string, save: boolean) => void;
}) {
  return (
    <div className="relative group">
      <div className="block bg-white border border-gray-200 rounded-xl overflow-hidden hover:shadow-md transition-shadow">
        {book.cover_image_url && (
          <div className="h-36 overflow-hidden bg-gray-100">
            <img
              src={book.cover_image_url}
              alt=""
              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
              loading="lazy"
            />
          </div>
        )}
        <div className="p-4">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <span className="text-xs bg-amber-50 text-amber-600 border border-amber-100 px-1.5 py-0.5 rounded font-medium">书</span>
            {book.source_category && (
              <span className="text-xs text-gray-400">
                {CATEGORIES.find((c) => c.value === book.source_category)?.label ?? book.source_category}
              </span>
            )}
          </div>
          <h3 className="font-medium text-sm leading-snug line-clamp-2 text-gray-800 group-hover:text-blue-600 transition-colors">
            {book.title}
          </h3>
          <p className="text-xs text-gray-400 mt-2">{book.chapter_count} 章</p>
        </div>
      </div>
      <button
        onClick={() => onSave(book.id, !book.is_saved)}
        className={`absolute top-2 right-2 p-1.5 rounded-full transition-all ${
          book.is_saved
            ? "bg-blue-50 text-blue-500"
            : "bg-white/80 text-gray-300 hover:text-blue-400 opacity-0 group-hover:opacity-100"
        } shadow-sm`}
        aria-label={book.is_saved ? "从书架移除" : "添加到书架"}
        title={book.is_saved ? "从书架移除" : "添加到书架"}
      >
        {book.is_saved ? <BookmarkCheck size={15} /> : <Bookmark size={15} />}
      </button>
    </div>
  );
}

export default function LibraryPage() {
  const [tab, setTab] = useState<"articles" | "books">("articles");
  const [category, setCategory] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 20;
  const queryClient = useQueryClient();

  const bookmarkMutation = useMutation({
    mutationFn: ({ id, bookmarked }: { id: string; bookmarked: boolean }) =>
      bookmarked
        ? api.post(`library/${id}/bookmark`).json()
        : api.delete(`library/${id}/bookmark`).json(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["library"] });
      queryClient.invalidateQueries({ queryKey: ["articles"] });
    },
  });

  const saveBookMutation = useMutation({
    mutationFn: ({ id, save }: { id: string; save: boolean }) =>
      save
        ? api.post(`library/books/${id}/save`).json()
        : api.delete(`library/books/${id}/save`).json(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["library-books"] });
      queryClient.invalidateQueries({ queryKey: ["books"] });
    },
  });

  const { data: articles, isLoading: articlesLoading } = useQuery({
    queryKey: ["library", category, difficulty, page],
    queryFn: () => {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      if (category) params.set("category", category);
      if (difficulty) params.set("difficulty", difficulty);
      return api.get(`library?${params}`).json<LibraryArticleListItem[]>();
    },
    enabled: tab === "articles",
  });

  const { data: libraryBooks, isLoading: booksLoading } = useQuery({
    queryKey: ["library-books"],
    queryFn: () => api.get("library/books").json<LibraryBookListItem[]>(),
    enabled: tab === "books",
  });

  function handleFilterChange(newCategory: string, newDifficulty: string) {
    setCategory(newCategory);
    setDifficulty(newDifficulty);
    setPage(1);
  }

  return (
    <div className="min-h-screen bg-white">
      <PageNav />
      <div className="max-w-4xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">内容库</h1>
            <p className="text-sm text-gray-400 mt-0.5">VOA Learning English 精选内容</p>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-6 border-b border-gray-100">
          <button
            onClick={() => setTab("articles")}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              tab === "articles"
                ? "border-blue-500 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            文章
          </button>
          <button
            onClick={() => setTab("books")}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              tab === "books"
                ? "border-blue-500 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            图书
          </button>
        </div>

        {/* Article filters (only shown on articles tab) */}
        {tab === "articles" && (
          <div className="flex flex-wrap gap-2 mb-6">
            <select
              value={category}
              onChange={(e) => handleFilterChange(e.target.value, difficulty)}
              className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
            >
              {CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
            <select
              value={difficulty}
              onChange={(e) => handleFilterChange(category, e.target.value)}
              className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
            >
              {DIFFICULTIES.map((d) => (
                <option key={d.value} value={d.value}>{d.label}</option>
              ))}
            </select>
          </div>
        )}

        {/* Articles tab content */}
        {tab === "articles" && (
          <>
            {articlesLoading && <p className="text-gray-400 text-sm">加载中...</p>}
            {!articlesLoading && articles?.length === 0 && (
              <div className="text-center text-gray-400 py-20">
                <p className="text-4xl mb-3">📚</p>
                <p className="font-medium">暂无文章</p>
                <p className="text-sm mt-1">内容库尚未同步，请在后台触发 VOA 同步</p>
              </div>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {articles?.map((article) => (
                <ArticleCard
                  key={article.id}
                  article={article}
                  onBookmark={(id, bookmarked) => bookmarkMutation.mutate({ id, bookmarked })}
                />
              ))}
            </div>
            {articles && (articles.length === pageSize || page > 1) && (
              <div className="flex items-center justify-center gap-3 mt-8">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="text-sm px-4 py-2 border border-gray-200 rounded-lg text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  上一页
                </button>
                <span className="text-sm text-gray-400">第 {page} 页</span>
                <button
                  onClick={() => setPage((p) => p + 1)}
                  disabled={articles.length < pageSize}
                  className="text-sm px-4 py-2 border border-gray-200 rounded-lg text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  下一页
                </button>
              </div>
            )}
          </>
        )}

        {/* Books tab content */}
        {tab === "books" && (
          <>
            {booksLoading && <p className="text-gray-400 text-sm">加载中...</p>}
            {!booksLoading && libraryBooks?.length === 0 && (
              <div className="text-center text-gray-400 py-20">
                <p className="text-4xl mb-3">📖</p>
                <p className="font-medium">暂无公共图书</p>
                <p className="text-sm mt-1">管理员尚未添加公共图书</p>
              </div>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {libraryBooks?.map((book) => (
                <BookCard
                  key={book.id}
                  book={book}
                  onSave={(id, save) => saveBookMutation.mutate({ id, save })}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
