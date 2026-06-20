import { useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { api } from "../api/client";
import type { BookDetail } from "../types";

export default function BookDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");

  const { data: book, isLoading } = useQuery({
    queryKey: ["book", id],
    queryFn: () => api.get(`books/${id}`).json<BookDetail>(),
    enabled: !!id,
  });

  const addChapter = useMutation({
    mutationFn: (body: { title: string; raw_text: string }) =>
      api.post(`books/${id}/chapters`, { json: body }).json(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["book", id] });
      setTitle("");
      setText("");
      setAdding(false);
    },
  });

  if (isLoading || !book) {
    return <div className="flex items-center justify-center h-screen text-gray-400">加载中...</div>;
  }

  return (
    <div className="min-h-screen bg-white">
      <div className="max-w-3xl mx-auto px-6 py-8">
        <Link to="/" className="inline-flex items-center gap-1 text-gray-400 hover:text-gray-600 text-sm mb-4">
          <ArrowLeft size={16} /> 返回
        </Link>
        <h1 className="text-2xl font-bold text-gray-900 mb-1">{book.title}</h1>
        <p className="text-sm text-gray-400 mb-6">{book.chapters.length} 章</p>

        {book.continue_article_id && (
          <button
            onClick={() => navigate(`/articles/${book.continue_article_id}`)}
            className="bg-blue-500 text-white px-5 py-2.5 rounded-lg text-sm font-medium hover:bg-blue-600 transition-colors mb-6"
          >
            继续阅读
          </button>
        )}

        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold text-gray-800">章节目录</h2>
          <button
            onClick={() => setAdding(!adding)}
            className="text-sm text-blue-500 hover:text-blue-600 font-medium"
          >
            + 添加章节
          </button>
        </div>

        {adding && (
          <div className="bg-gray-50 rounded-xl border border-gray-200 p-5 mb-5">
            <input
              type="text" value={title} onChange={(e) => setTitle(e.target.value)}
              placeholder="章节标题"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 mb-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
            <textarea
              value={text} onChange={(e) => setText(e.target.value)}
              placeholder="在此粘贴本章英文..." rows={10}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 mb-4 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-400 resize-none"
            />
            <div className="flex gap-2">
              <button
                onClick={() => addChapter.mutate({ title, raw_text: text })}
                disabled={!title.trim() || !text.trim() || addChapter.isPending}
                className="bg-blue-500 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-600 disabled:opacity-50"
              >
                {addChapter.isPending ? "处理中..." : "提交"}
              </button>
              <button onClick={() => setAdding(false)} className="bg-gray-200 text-gray-700 px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-300">
                取消
              </button>
            </div>
          </div>
        )}

        <div className="space-y-2">
          {book.chapters.map((ch) => (
            <Link
              key={ch.id} to={`/articles/${ch.id}`}
              className="flex items-center justify-between bg-white border border-gray-200 rounded-xl p-4 hover:shadow-sm transition-shadow"
            >
              <div className="min-w-0">
                <span className="text-xs text-gray-400 mr-2">第 {ch.chapter_order} 章</span>
                <span className="font-medium text-gray-800">{ch.title}</span>
              </div>
              <span className="text-xs text-gray-400 shrink-0 ml-3">
                {ch.last_sentence_index != null ? "已读" : ""} {ch.word_count.toLocaleString()} 词
              </span>
            </Link>
          ))}
          {book.chapters.length === 0 && (
            <p className="text-center text-gray-400 py-12 text-sm">还没有章节，点击「+ 添加章节」开始</p>
          )}
        </div>
      </div>
    </div>
  );
}
