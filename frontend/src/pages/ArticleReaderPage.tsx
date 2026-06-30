import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, Languages, Loader2, Pencil, RotateCcw, X } from "lucide-react";
import { api } from "../api/client";
import { useAnnotationStore } from "../store/annotationStore";
import { useSidebarStore } from "../store/sidebarStore";
import { ArticleBody } from "../components/ArticleBody";
import { WordSidebar } from "../components/WordSidebar";
import type { ArticleDetail, ArticleTranslateResponse, AppSettings } from "../types";

export default function ArticleReaderPage() {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const targetSentence = searchParams.get("sentence");
  const queryClient = useQueryClient();
  const { initFromArticle } = useAnnotationStore();
  const { close: closeSidebar } = useSidebarStore();
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editText, setEditText] = useState("");

  // Close sidebar when leaving the page
  useEffect(() => () => closeSidebar(), [closeSidebar]);

  const { data: article, isLoading, isError } = useQuery({
    queryKey: ["article", id],
    queryFn: () => api.get(`articles/${id}`).json<ArticleDetail>(),
    enabled: !!id,
    refetchInterval: (query) =>
      query.state.data?.translation_status === "processing" ? 2500 : false,
  });

  const { data: settings } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get("settings").json<AppSettings>(),
    staleTime: Infinity,
  });

  // Seed annotation cache once on load
  useEffect(() => {
    if (article) {
      initFromArticle(article.id, article.annotations);
    }
  }, [article]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (article && !isEditing) {
      setEditTitle(article.title);
      setEditText(article.raw_text);
    }
  }, [article, isEditing]);

  // Scroll to ?sentence= target or last-read sentence
  useEffect(() => {
    if (!article) return;
    const idx = targetSentence != null ? Number(targetSentence) : article.last_sentence_index;
    if (idx && idx > 0) {
      const t = setTimeout(() => {
        document.querySelector(`[data-sentence-index="${idx}"]`)
          ?.scrollIntoView({ behavior: "auto", block: "center" });
      }, 100);
      return () => clearTimeout(t);
    }
  }, [article, targetSentence]);

  const progressMutation = useMutation({
    mutationFn: (body: { last_sentence_index: number }) =>
      api.put(`articles/${id}/progress`, { json: body }),
  });

  const pretranslateMutation = useMutation({
    mutationFn: () => api.post(`articles/${id}/translate`).json<ArticleTranslateResponse>(),
    onSuccess: (data) => {
      queryClient.setQueryData<ArticleDetail>(["article", id], (current) =>
        current
          ? {
              ...current,
              translation_status: data.translation_status,
              translation_progress: data.translation_progress,
            }
          : current
      );
    },
  });

  const updateMutation = useMutation({
    mutationFn: (body: { title: string; raw_text: string }) =>
      api.put(`articles/${id}`, { json: body }).json<ArticleDetail>(),
    onSuccess: (data) => {
      queryClient.setQueryData<ArticleDetail>(["article", id], data);
      queryClient.invalidateQueries({ queryKey: ["articles"] });
      initFromArticle(data.id, data.annotations);
      setIsEditing(false);
    },
  });

  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const container = e.currentTarget;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      const anchors = container.querySelectorAll("[data-sentence-index]");
      const top = container.getBoundingClientRect().top;
      let current = 0;
      for (const a of Array.from(anchors)) {
        if (a.getBoundingClientRect().top <= top + 80) {
          current = Number((a as HTMLElement).dataset.sentenceIndex);
        } else break;
      }
      if (id) progressMutation.mutate({ last_sentence_index: current });
    }, 600);
  };

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

  const translationProgress = article.translation_progress;
  const hasTranslationProgress = translationProgress.total_words > 0;
  const canResumeTranslation =
    article.translation_status === "failed" && translationProgress.processed_words > 0;
  const pretranslateLabel = canResumeTranslation
    ? "继续预翻译"
    : article.translation_status === "failed"
      ? "重试"
      : "预翻译";
  const canSaveEdit =
    editTitle.trim().length > 0 &&
    editText.trim().length > 0 &&
    !updateMutation.isPending;

  return (
    <div className="flex h-screen bg-white">
      {/* Main reading area */}
      <div className="flex-1 overflow-y-auto" onScroll={handleScroll}>
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
          <div className="ml-auto flex items-center gap-3">
            <span className="text-xs text-gray-400">{article.word_count.toLocaleString()} 词</span>
            {isEditing ? (
              <>
                <button
                  onClick={() =>
                    updateMutation.mutate({
                      title: editTitle.trim(),
                      raw_text: editText,
                    })
                  }
                  disabled={!canSaveEdit}
                  className="inline-flex items-center gap-1.5 rounded-md border border-blue-200 px-2.5 py-1.5 text-xs font-medium text-blue-600 hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {updateMutation.isPending ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Check size={14} />
                  )}
                  保存
                </button>
                <button
                  onClick={() => {
                    setEditTitle(article.title);
                    setEditText(article.raw_text);
                    setIsEditing(false);
                  }}
                  disabled={updateMutation.isPending}
                  className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 px-2.5 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <X size={14} />
                  取消
                </button>
              </>
            ) : (
              <button
                onClick={() => setIsEditing(true)}
                disabled={article.translation_status === "processing"}
                className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 px-2.5 py-1.5 text-xs font-medium text-gray-600 hover:border-blue-200 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Pencil size={14} />
                编辑
              </button>
            )}
            {article.translation_status !== "done" && (
              <button
                onClick={() => pretranslateMutation.mutate()}
                disabled={
                  isEditing ||
                  article.translation_status === "processing" ||
                  pretranslateMutation.isPending
                }
                className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 px-2.5 py-1.5 text-xs font-medium text-gray-600 hover:border-blue-200 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {article.translation_status === "processing" || pretranslateMutation.isPending ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : article.translation_status === "failed" ? (
                  <RotateCcw size={14} />
                ) : (
                  <Languages size={14} />
                )}
                {pretranslateLabel}
              </button>
            )}
          </div>
        </div>

        {article.translation_status === "processing" && (
          <div className="border-b border-blue-100 bg-blue-50 px-6 py-2 text-xs text-blue-700">
            <div className="mx-auto flex max-w-2xl items-center gap-3">
              <span className="shrink-0">预翻译 {hasTranslationProgress ? `${translationProgress.percent}%` : "准备中"}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-blue-100">
                <div
                  className="h-full rounded-full bg-blue-500 transition-all"
                  style={{ width: `${hasTranslationProgress ? translationProgress.percent : 2}%` }}
                />
              </div>
              {hasTranslationProgress && (
                <span className="shrink-0 text-blue-500">
                  {translationProgress.processed_words}/{translationProgress.total_words} 词 ·{" "}
                  {translationProgress.completed_chunks}/{translationProgress.total_chunks}
                </span>
              )}
            </div>
          </div>
        )}
        {article.translation_status === "failed" && (
          <div className="border-b border-red-100 bg-red-50 px-6 py-2 text-xs text-red-600">
            <div className="mx-auto flex max-w-2xl items-center justify-between gap-3">
              <span>{canResumeTranslation ? "预翻译中断，可继续" : "预翻译失败，请重试"}</span>
              {hasTranslationProgress && (
                <span className="text-red-500">
                  {translationProgress.percent}% · {translationProgress.processed_words}/{translationProgress.total_words} 词
                </span>
              )}
            </div>
          </div>
        )}

        {/* Article content */}
        <div className="max-w-2xl mx-auto px-8 py-10">
          {isEditing ? (
            <div className="space-y-4">
              <input
                value={editTitle}
                onChange={(event) => setEditTitle(event.target.value)}
                className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm font-medium text-gray-800 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
              />
              <textarea
                value={editText}
                onChange={(event) => setEditText(event.target.value)}
                rows={20}
                className="min-h-[520px] w-full resize-y rounded-md border border-gray-200 px-3 py-3 font-mono text-sm leading-6 text-gray-800 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
              />
              {updateMutation.isError && (
                <p className="text-xs text-red-500">
                  {(updateMutation.error as Error).message}
                </p>
              )}
            </div>
          ) : (
            <ArticleBody
              paragraphs={article.paragraphs}
              articleId={article.id}
              autoOpenSidebar={settings?.auto_open_sidebar_on_mark ?? true}
            />
          )}
        </div>
      </div>

      {/* Sidebar */}
      <WordSidebar />
    </div>
  );
}
