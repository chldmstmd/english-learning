import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { PageNav } from "../components/PageNav";
import { WordSidebar } from "../components/WordSidebar";
import { useSidebarStore } from "../store/sidebarStore";
import { useVocabStore } from "../store/vocabStore";
import type { VocabItem, WordStatus } from "../types";

const STATUS_LABELS: Record<WordStatus | "all", string> = {
  all: "全部",
  unseen: "",
  new: "新词",
  reviewing: "巩固中",
  mastered: "已习得",
};

const STATUS_BADGE: Record<WordStatus, string> = {
  unseen: "",
  new: "bg-red-50 text-red-600",
  reviewing: "bg-yellow-50 text-yellow-700",
  mastered: "bg-gray-100 text-gray-500",
};

export default function VocabListPage() {
  const [filter, setFilter] = useState<WordStatus | "all">("all");
  const { open: openSidebar } = useSidebarStore();
  const { setWordStatus } = useVocabStore();
  const queryClient = useQueryClient();

  const queryParams = filter === "all" ? {} : { status: filter };
  const { data: words, isLoading } = useQuery({
    queryKey: ["vocab", filter],
    queryFn: () =>
      api.get("vocab", { searchParams: queryParams }).json<VocabItem[]>(),
  });

  const statusMutation = useMutation({
    mutationFn: ({ word, status }: { word: string; status: WordStatus | "unseen" }) => {
      if (status === "unseen") {
        return api.delete(`vocab/${word}`);
      }
      return api.patch(`vocab/${word}/status`, {
        json: { status },
        searchParams: { force: "true" },
      });
    },
    onSuccess: (_, { word, status }) => {
      queryClient.invalidateQueries({ queryKey: ["vocab"] });
      if (status === "unseen") {
        // uncollect deletes this lemma's position annotations server-side;
        // refetch articles so the reader drops the stale head-of-word translation.
        queryClient.invalidateQueries({ queryKey: ["article"] });
        queryClient.invalidateQueries({ queryKey: ["library-article"] });
      }
      setWordStatus(word, status === "unseen" ? "unseen" : status);
    },
  });

  return (
    <div className="min-h-screen bg-white">
      <PageNav />
      <WordSidebar />

      <div className="max-w-3xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900">生词表</h1>
          <span className="text-sm text-gray-400">{words?.length ?? 0} 个单词</span>
        </div>

        {/* Filter tabs */}
        <div className="flex gap-1 mb-6">
          {(["all", "new", "reviewing", "mastered"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                filter === s
                  ? "bg-gray-900 text-white"
                  : "text-gray-500 hover:text-gray-700 hover:bg-gray-100"
              }`}
            >
              {STATUS_LABELS[s]}
            </button>
          ))}
        </div>

        {isLoading && <p className="text-gray-400 text-sm">加载中...</p>}

        <div className="divide-y divide-gray-100">
          {words?.map((item) => (
            <div
              key={item.id}
              className="flex items-center gap-4 py-3 hover:bg-gray-50 -mx-2 px-2 rounded-lg cursor-pointer transition-colors"
              onClick={() =>
                openSidebar(item.word, item.word, "", item.context_translation ?? "")
              }
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-gray-900">{item.word}</span>
                  {item.status !== "unseen" && (
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded ${STATUS_BADGE[item.status]}`}
                    >
                      {STATUS_LABELS[item.status]}
                    </span>
                  )}
                </div>
                <p className="text-sm text-gray-500 mt-0.5 truncate">
                  {item.context_translation ?? "打开查看释义"}
                </p>
              </div>

              {/* Status selector */}
              <div className="shrink-0" onClick={(e) => e.stopPropagation()}>
                <select
                  value={item.status}
                  onChange={(e) =>
                    statusMutation.mutate({
                      word: item.word,
                      status: e.target.value as WordStatus | "unseen",
                    })
                  }
                  className="text-xs border border-gray-200 rounded px-2 py-1 bg-white text-gray-600 cursor-pointer focus:outline-none focus:ring-1 focus:ring-blue-400"
                >
                  <option value="unseen">未收录</option>
                  <option value="new">新词</option>
                  <option value="reviewing">巩固中</option>
                  <option value="mastered">已习得</option>
                </select>
              </div>
            </div>
          ))}
        </div>

        {!isLoading && words?.length === 0 && (
          <div className="text-center text-gray-400 py-20">
            <p className="text-4xl mb-3">📚</p>
            <p className="font-medium">
              {filter === "all" ? "还没有生词" : `没有「${STATUS_LABELS[filter]}」状态的词`}
            </p>
            {filter === "all" && (
              <p className="text-sm mt-1">阅读文章并点击陌生单词来添加生词</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
