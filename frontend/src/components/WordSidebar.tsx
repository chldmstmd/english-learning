import React, { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { X, Volume2, ArrowRight } from "lucide-react";
import { api } from "../api/client";
import { useSidebarStore } from "../store/sidebarStore";
import { useVocabStore } from "../store/vocabStore";
import type { VocabDetail } from "../types";

function speak(text: string) {
  if ("speechSynthesis" in window) {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "en-US";
    window.speechSynthesis.speak(utterance);
  }
}

export const WordSidebar: React.FC = () => {
  const { isOpen, word, lemma, sourceSentence, close } = useSidebarStore();
  const { setWordStatus } = useVocabStore();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [close]);

  const { data: detail, isLoading } = useQuery({
    queryKey: ["vocab-detail", lemma, sourceSentence],
    queryFn: () =>
      api
        .get(`vocab/${lemma}/detail`, {
          searchParams: sourceSentence ? { sentence: sourceSentence } : {},
        })
        .json<VocabDetail>(),
    enabled: isOpen && !!lemma,
    staleTime: 60_000,
  });

  const statusMutation = useMutation({
    mutationFn: ({ word, status }: { word: string; status: string }) =>
      api.patch(`vocab/${word}/status`, { json: { status }, searchParams: { force: "true" } }),
    onSuccess: (_, { word: w, status }) => {
      setWordStatus(w, status as never);
      queryClient.invalidateQueries({ queryKey: ["vocab-detail", w] });
      queryClient.invalidateQueries({ queryKey: ["vocab"] });
    },
  });

  const goToLocation = (loc: VocabDetail["locations"][number]) => {
    const base = loc.is_library ? "/library" : "/articles";
    close();
    navigate(`${base}/${loc.article_id}?sentence=${loc.sentence_index}`);
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.aside
          key="sidebar"
          initial={{ x: "100%" }}
          animate={{ x: 0 }}
          exit={{ x: "100%" }}
          transition={{ type: "tween", duration: 0.2 }}
          className="fixed right-0 top-0 h-full w-80 bg-white border-l border-gray-200 shadow-xl flex flex-col z-50 overflow-y-auto"
        >
          {/* Header */}
          <div className="flex items-center justify-between p-5 border-b border-gray-100">
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-bold text-gray-900">{word}</h2>
              {detail?.phonetic && (
                <span className="text-sm text-gray-400">{detail.phonetic}</span>
              )}
              <button
                onClick={() => word && speak(word)}
                className="text-blue-400 hover:text-blue-600"
                aria-label="朗读"
              >
                <Volume2 size={16} />
              </button>
            </div>
            <button
              onClick={close}
              className="text-gray-400 hover:text-gray-600"
              aria-label="关闭"
            >
              <X size={20} />
            </button>
          </div>

          <div className="flex-1 p-5 flex flex-col gap-5">
            {/* Chinese meaning (dictionary, word-level) — always shown once detail loads */}
            {detail && (
              <div className="bg-gray-50 border border-gray-100 rounded-lg p-4">
                <p className="text-xs text-gray-500 mb-1 uppercase tracking-wide">中文词义</p>
                <p className="text-lg font-semibold text-gray-900">
                  {detail.context_translation ?? "打开查看释义"}
                </p>
              </div>
            )}

            {isLoading && (
              <p className="text-sm text-gray-400 animate-pulse">加载中...</p>
            )}

            {/* English dictionary definitions */}
            {detail?.definitions && detail.definitions.length > 0 && (
              <section>
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
                  词典释义
                </h3>
                <div className="space-y-2">
                  {detail.definitions.map((def, i) => (
                    <div key={i}>
                      <span className="text-xs bg-gray-100 text-gray-500 rounded px-1.5 py-0.5 mr-1.5">
                        {def.pos}
                      </span>
                      <span className="text-sm text-gray-700">{def.definition}</span>
                      {def.example && (
                        <p className="text-xs text-gray-400 mt-0.5 italic pl-1">
                          {def.example}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Click locations */}
            {detail?.locations && detail.locations.length > 0 && (
              <section>
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
                  你点过的位置
                </h3>
                <div className="space-y-2">
                  {detail.locations.map((loc, i) => (
                    <button
                      key={i}
                      onClick={() => goToLocation(loc)}
                      className="w-full text-left border border-gray-200 rounded-lg p-2.5 hover:border-amber-400 transition-colors group"
                    >
                      <div className="flex items-center gap-1.5 text-xs font-medium text-gray-700">
                        <span className="truncate">{loc.article_title}</span>
                        {loc.is_stale && (
                          <span className="text-amber-600 shrink-0">(原文已修改)</span>
                        )}
                        <ArrowRight size={11} className="ml-auto shrink-0 text-gray-300 group-hover:text-amber-500" />
                      </div>
                      {loc.source_sentence && (
                        <p className="text-xs text-gray-400 mt-0.5 line-clamp-2">{loc.source_sentence}</p>
                      )}
                    </button>
                  ))}
                </div>
              </section>
            )}
          </div>

          {/* Status actions — pinned to bottom */}
          {detail && detail.status !== "unseen" && (
            <div className="p-5 border-t border-gray-100 flex gap-2">
              {detail.status !== "mastered" ? (
                <button
                  onClick={() => {
                    if (lemma) statusMutation.mutate({ word: lemma, status: "mastered" });
                    close();
                  }}
                  className="flex-1 bg-green-500 text-white rounded-lg py-2.5 text-sm font-medium hover:bg-green-600 transition-colors"
                >
                  标记已掌握
                </button>
              ) : (
                <button
                  onClick={() => {
                    if (lemma) statusMutation.mutate({ word: lemma, status: "new" });
                    close();
                  }}
                  className="flex-1 bg-gray-100 text-gray-700 rounded-lg py-2.5 text-sm font-medium hover:bg-gray-200 transition-colors"
                >
                  重新加入学习
                </button>
              )}
            </div>
          )}
        </motion.aside>
      )}
    </AnimatePresence>
  );
};
