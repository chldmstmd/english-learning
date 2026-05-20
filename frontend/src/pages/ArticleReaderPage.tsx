import { useEffect, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { api } from "../api/client";
import { useVocabStore } from "../store/vocabStore";
import { useSidebarStore } from "../store/sidebarStore";
import { ArticleBody } from "../components/ArticleBody";
import { WordSidebar } from "../components/WordSidebar";
import type { ArticleDetail, Annotation, AppSettings } from "../types";

export default function ArticleReaderPage() {
  const { id } = useParams<{ id: string }>();
  const { initFromArticle, mergeAnnotations, articleAnnotations } = useVocabStore();
  const { close: closeSidebar } = useSidebarStore();

  // Close sidebar when leaving the page
  useEffect(() => () => closeSidebar(), [closeSidebar]);

  const { data: article, isLoading, isError } = useQuery({
    queryKey: ["article", id],
    queryFn: () => api.get(`articles/${id}`).json<ArticleDetail>(),
    enabled: !!id,
  });

  const { data: settings } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get("settings").json<AppSettings>(),
    staleTime: Infinity,
  });

  // Seed the vocab store once on load
  useEffect(() => {
    if (article) {
      initFromArticle(article.id, article.word_statuses, article.annotations);
    }
  }, [article]); // eslint-disable-line react-hooks/exhaustive-deps

  // Poll for pending annotations (every 2s until all done)
  const hasPending = useMemo(() => {
    if (!id || !articleAnnotations[id]) return false;
    return Object.values(articleAnnotations[id]).some((a) => a.gen_status === "pending");
  }, [id, articleAnnotations]);

  useQuery({
    queryKey: ["annotations-poll", id],
    queryFn: async () => {
      const anns = await api
        .get(`articles/${id}/annotations`)
        .json<Record<string, Annotation>>();
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
        <Link to="/" className="text-blue-500 hover:underline text-sm">
          返回列表
        </Link>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-white">
      {/* Main reading area */}
      <div className="flex-1 overflow-y-auto">
        {/* Top bar */}
        <div className="sticky top-0 bg-white/90 backdrop-blur border-b border-gray-100 px-6 py-3 flex items-center gap-3 z-10">
          <Link
            to="/"
            className="text-gray-400 hover:text-gray-600 transition-colors"
            aria-label="返回列表"
          >
            <ArrowLeft size={18} />
          </Link>
          <h1 className="text-sm font-medium text-gray-700 truncate">{article.title}</h1>
          <span className="ml-auto text-xs text-gray-400">{article.word_count.toLocaleString()} 词</span>
        </div>

        {article.translation_status === "processing" && (
          <div className="bg-blue-50 text-blue-600 text-xs text-center py-1.5">
            正在准备翻译缓存...
          </div>
        )}

        {/* Article content */}
        <div className="max-w-2xl mx-auto px-8 py-10">
          <ArticleBody
            tokens={article.tokens}
            sentences={article.sentences}
            articleId={article.id}
            autoOpenSidebar={settings?.auto_open_sidebar_on_mark ?? true}
          />
        </div>
      </div>

      {/* Sidebar */}
      <WordSidebar />
    </div>
  );
}
