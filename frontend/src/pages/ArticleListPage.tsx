import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { PageNav } from "../components/PageNav";
import type { ArticleListItem } from "../types";

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
              <Link to={`/articles/${article.id}`} className="flex-1 min-w-0">
                <h3 className="font-medium text-gray-800 hover:text-blue-600 truncate">
                  {article.title}
                </h3>
                <p className="text-xs text-gray-400 mt-0.5">
                  {article.word_count.toLocaleString()} 词 ·{" "}
                  {new Date(article.created_at).toLocaleDateString("zh-CN")}
                </p>
              </Link>
              <button
                onClick={() => {
                  if (confirm(`确认删除「${article.title}」？此操作不可撤销。`)) {
                    deleteMutation.mutate(article.id);
                  }
                }}
                className="ml-4 text-gray-300 hover:text-red-400 transition-colors text-sm shrink-0"
              >
                删除
              </button>
            </div>
          ))}
        </div>

        {!isLoading && articles?.length === 0 && (
          <div className="text-center text-gray-400 py-20">
            <p className="font-medium">还没有文章</p>
            <p className="text-sm mt-1">点击右上角添加文章，粘贴一段英文来测试语境翻译。</p>
          </div>
        )}
      </div>
    </div>
  );
}
