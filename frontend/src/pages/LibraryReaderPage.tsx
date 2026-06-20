import { useEffect, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Bookmark, BookmarkCheck, ExternalLink } from "lucide-react";
import { api } from "../api/client";
import { useVocabStore } from "../store/vocabStore";
import { useSidebarStore } from "../store/sidebarStore";
import { ArticleBody } from "../components/ArticleBody";
import { WordSidebar } from "../components/WordSidebar";
import type { ArticleDetail, AppSettings, Difficulty } from "../types";

const DIFFICULTY_LABELS: Record<Difficulty, string> = {
  level1: "Level 1 · 慢速英语",
  level2: "Level 2 · 标准英语",
};

export default function LibraryReaderPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const { initFromArticle, mergeAnnotations, articleAnnotations } = useVocabStore();
  const { close: closeSidebar } = useSidebarStore();
  const [showBookmarkPrompt, setShowBookmarkPrompt] = useState(false);

  const bookmarkMutation = useMutation({
    mutationFn: (bookmarked: boolean) =>
      bookmarked
        ? api.post(`library/${id}/bookmark`).json()
        : api.delete(`library/${id}/bookmark`).json(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["library-article", id] });
      queryClient.invalidateQueries({ queryKey: ["articles"] });
      queryClient.invalidateQueries({ queryKey: ["library"] });
    },
  });

  useEffect(() => () => closeSidebar(), [closeSidebar]);

  const { data: article, isLoading, isError } = useQuery({
    queryKey: ["library-article", id],
    queryFn: () => api.get(`library/${id}`).json<ArticleDetail>(),
    enabled: !!id,
  });

  const { data: settings } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get("settings").json<AppSettings>(),
    staleTime: Infinity,
  });

  useEffect(() => {
    if (article) {
      initFromArticle(article.id, article.word_statuses, article.annotations);
    }
  }, [article]); // eslint-disable-line react-hooks/exhaustive-deps

  // Show one-time bookmark prompt when user marks their first word in an un-bookmarked library article
  useEffect(() => {
    if (!id || !article || article.is_bookmarked) return;
    const annotations = articleAnnotations[id];
    if (!annotations || Object.keys(annotations).length === 0) return;

    const promptedKey = "bookmark_prompted_articles";
    let prompted: string[] = [];
    try {
      prompted = JSON.parse(localStorage.getItem(promptedKey) ?? "[]");
    } catch { /* ignore */ }
    if (prompted.includes(id)) return;

    prompted.push(id);
    localStorage.setItem(promptedKey, JSON.stringify(prompted));
    setShowBookmarkPrompt(true);
  }, [id, article?.is_bookmarked, articleAnnotations]); // eslint-disable-line react-hooks/exhaustive-deps

  const hasPending = useMemo(() => {
    if (!id || !articleAnnotations[id]) return false;
    return Object.values(articleAnnotations[id]).some((a) => a.gen_status === "pending");
  }, [id, articleAnnotations]);

  useQuery({
    queryKey: ["library-annotations-poll", id],
    queryFn: async () => {
      // Library articles share the same annotation endpoint as user articles
      const anns = await api
        .get(`articles/${id}/annotations`)
        .json<Record<string, import("../types").Annotation>>();
      if (id) mergeAnnotations(id, anns);
      return anns;
    },
    enabled: !!id && hasPending,
    refetchInterval: 2000,
    refetchIntervalInBackground: false,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen text-gray-400">
        加载中...
      </div>
    );
  }

  if (isError || !article) {
    return (
      <div className="flex flex-col items-center justify-center h-screen text-gray-500 gap-4">
        <p>文章加载失败</p>
        <Link to="/library" className="text-blue-500 hover:underline text-sm">
          返回内容库
        </Link>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-white">
      <div className="flex-1 overflow-y-auto">
        {/* Top bar */}
        <div className="sticky top-0 bg-white/90 backdrop-blur border-b border-gray-100 px-6 py-3 flex items-center gap-3 z-10">
          <Link
            to="/library"
            className="text-gray-400 hover:text-gray-600 transition-colors"
            aria-label="返回内容库"
          >
            <ArrowLeft size={18} />
          </Link>
          <h1 className="text-sm font-medium text-gray-700 truncate">{article.title}</h1>
          <div className="ml-auto flex items-center gap-3">
            <span className="text-xs text-gray-400">{article.word_count.toLocaleString()} 词</span>
            <button
              onClick={() => bookmarkMutation.mutate(!article.is_bookmarked)}
              disabled={bookmarkMutation.isPending}
              className={`flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg font-medium transition-colors disabled:opacity-50 ${
                article.is_bookmarked
                  ? "bg-blue-500 text-white hover:bg-blue-600"
                  : "border border-gray-200 text-gray-500 hover:border-blue-400 hover:text-blue-500"
              }`}
              aria-label={article.is_bookmarked ? "取消收藏" : "收藏到文章列表"}
            >
              {article.is_bookmarked
                ? <><BookmarkCheck size={15} /> 已收藏</>
                : <><Bookmark size={15} /> 收藏</>
              }
            </button>
          </div>
        </div>

        {/* Article metadata banner */}
        {(article.difficulty || article.published_at || article.source_url) && (
          <div className="max-w-2xl mx-auto px-8 pt-6">
            <div className="flex items-center gap-3 py-2.5 px-4 bg-gray-50 rounded-lg border border-gray-100 text-xs text-gray-500">
              {article.difficulty && (
                <span>{DIFFICULTY_LABELS[article.difficulty]}</span>
              )}
              {article.published_at && (
                <>
                  {article.difficulty && <span>·</span>}
                  <span>{new Date(article.published_at).toLocaleDateString("zh-CN")}</span>
                </>
              )}
              {article.source_url && (
                <a
                  href={article.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ml-auto flex items-center gap-1 text-blue-500 hover:text-blue-700 transition-colors"
                >
                  原文
                  <ExternalLink size={11} />
                </a>
              )}
            </div>
          </div>
        )}

        {/* Article content */}
        <div className="max-w-2xl mx-auto px-8 py-6">
          <ArticleBody
            tokens={article.tokens}
            sentences={article.sentences}
            articleId={article.id}
            autoOpenSidebar={settings?.auto_open_sidebar_on_mark ?? true}
          />
        </div>
      </div>

      <WordSidebar />

      {/* One-time bookmark prompt */}
      {showBookmarkPrompt && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-white border border-gray-200 rounded-xl shadow-lg px-5 py-4 flex items-center gap-4 max-w-sm w-full mx-4">
          <div className="flex-1">
            <p className="text-sm font-medium text-gray-800">收藏这篇文章？</p>
            <p className="text-xs text-gray-400 mt-0.5">收藏后可在"文章"列表快速找到</p>
          </div>
          <div className="flex gap-2 shrink-0">
            <button
              onClick={() => {
                bookmarkMutation.mutate(true);
                setShowBookmarkPrompt(false);
              }}
              className="text-sm px-3 py-1.5 bg-blue-500 text-white rounded-lg font-medium hover:bg-blue-600 transition-colors"
            >
              收藏
            </button>
            <button
              onClick={() => setShowBookmarkPrompt(false)}
              className="text-sm px-3 py-1.5 text-gray-400 hover:text-gray-600 transition-colors"
            >
              跳过
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
