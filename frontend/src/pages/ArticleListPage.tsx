import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { PageNav } from "../components/PageNav";
import type { ArticleListItem } from "../types";

const CATEGORY_LABELS: Record<string, string> = {
  "science-technology": "科技",
  "health-lifestyle": "健康",
  "us-history": "美国历史",
  "words-stories": "词汇故事",
};

export default function ArticleListPage() {
  const queryClient = useQueryClient();
  const [isCreating, setIsCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");

  const { data: articles, isLoading } = useQuery({
    queryKey: ["articles"],
    queryFn: () => api.get("articles").json<ArticleListItem[]>(),
  });

  const createMutation = useMutation({
    mutationFn: (body: { title: string; raw_text: string }) =>
      api.post("articles", { json: body }).json<ArticleListItem>(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["articles"] });
      setTitle("");
      setText("");
      setIsCreating(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`articles/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["articles"] }),
  });

  const unbookmarkMutation = useMutation({
    mutationFn: (id: string) => api.delete(`library/${id}/bookmark`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["articles"] }),
  });

  function handleRemove(article: ArticleListItem) {
    if (article.is_library) {
      if (confirm(`从列表中移除「${article.title}」？\n随时可在内容库重新收藏。`)) {
        unbookmarkMutation.mutate(article.id);
      }
    } else {
      if (confirm(`确认删除「${article.title}」？此操作不可撤销。`)) {
        deleteMutation.mutate(article.id);
      }
    }
  }

  return (
    <div className="min-h-screen bg-white">
      <PageNav />
      <div className="max-w-3xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-2xl font-bold text-gray-900">文章</h1>
          <button
            onClick={() => setIsCreating(!isCreating)}
            className="bg-blue-500 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-600 transition-colors"
          >
            + 添加文章
          </button>
        </div>

        {isCreating && (
          <div className="bg-gray-50 rounded-xl border border-gray-200 p-6 mb-6">
            <h2 className="font-semibold text-gray-800 mb-4">添加新文章</h2>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="文章标题"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 mb-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="在此粘贴英文文章..."
              rows={12}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 mb-4 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-400 resize-none"
            />
            {createMutation.isError && (
              <p className="text-red-500 text-xs mb-3">
                {(createMutation.error as Error).message}
              </p>
            )}
            <div className="flex gap-2">
              <button
                onClick={() => createMutation.mutate({ title, raw_text: text })}
                disabled={!title.trim() || !text.trim() || createMutation.isPending}
                className="bg-blue-500 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-600 disabled:opacity-50 transition-colors"
              >
                {createMutation.isPending ? "处理中..." : "提交"}
              </button>
              <button
                onClick={() => setIsCreating(false)}
                className="bg-gray-200 text-gray-700 px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-300 transition-colors"
              >
                取消
              </button>
            </div>
          </div>
        )}

        {isLoading && <p className="text-gray-400 text-sm">加载中...</p>}

        <div className="space-y-3">
          {articles?.map((article) => (
            <div
              key={article.id}
              className="flex items-center justify-between bg-white border border-gray-200 rounded-xl p-4 hover:shadow-sm transition-shadow"
            >
              <Link
                to={article.is_library ? `/library/${article.id}` : `/articles/${article.id}`}
                className="flex-1 min-w-0"
              >
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="font-medium text-gray-800 hover:text-blue-600 truncate">
                    {article.title}
                  </h3>
                  {article.is_library && (
                    <span className="shrink-0 text-xs bg-blue-50 text-blue-600 border border-blue-100 px-1.5 py-0.5 rounded font-medium">
                      VOA
                    </span>
                  )}
                  {article.is_library && article.source_category && (
                    <span className="shrink-0 text-xs text-gray-400">
                      {CATEGORY_LABELS[article.source_category] ?? article.source_category}
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-400 mt-0.5">
                  {article.word_count.toLocaleString()} 词 ·{" "}
                  {new Date(article.created_at).toLocaleDateString("zh-CN")}
                </p>
              </Link>
              <button
                onClick={() => handleRemove(article)}
                className="ml-4 text-gray-300 hover:text-red-400 transition-colors text-sm"
              >
                {article.is_library ? "移除" : "删除"}
              </button>
            </div>
          ))}
        </div>

        {!isLoading && articles?.length === 0 && (
          <div className="text-center text-gray-400 py-20">
            <p className="text-4xl mb-3">📖</p>
            <p className="font-medium">还没有文章</p>
            <p className="text-sm mt-1">
              点击右上角"添加文章"，或前往
              <Link to="/library" className="text-blue-500 hover:underline mx-1">内容库</Link>
              收藏文章
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
