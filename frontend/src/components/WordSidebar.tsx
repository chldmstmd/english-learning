import React, { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { X, Volume2 } from "lucide-react";
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

  // Close on Escape key
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
      api.patch(`vocab/${word}/status`, { json: { status } }),
    onSuccess: (_, { word: w, status }) => {
      setWordStatus(w, status as never);
      queryClient.invalidateQueries({ queryKey: ["vocab-detail", w] });
      queryClient.invalidateQueries({ queryKey: ["vocab"] });
    },
  });

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
            {/* Reviewing state: show translation prominently as "reveal" */}
            {detail?.status === "reviewing" && detail.context_translation && (
              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                <p className="text-xs text-gray-500 mb-1 uppercase tracking-wide">语境翻译</p>
                <p className="text-lg font-semibold text-gray-900">{detail.context_translation}</p>
              </div>
            )}

            {isLoading && (
              <p className="text-sm text-gray-400 animate-pulse">加载中...</p>
            )}

            {/* Dictionary definitions */}
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
          </div>

          {/* Reviewing actions — pinned to bottom */}
          {detail?.status === "reviewing" && (
            <div className="p-5 border-t border-gray-100 flex gap-2">
              <button
                onClick={() => {
                  if (lemma) statusMutation.mutate({ word: lemma, status: "mastered" });
                  close();
                }}
                className="flex-1 bg-green-500 text-white rounded-lg py-2.5 text-sm font-medium hover:bg-green-600 transition-colors"
              >
                已掌握
              </button>
              <button
                onClick={close}
                className="flex-1 bg-gray-100 text-gray-700 rounded-lg py-2.5 text-sm font-medium hover:bg-gray-200 transition-colors"
              >
                再复习一次
              </button>
            </div>
          )}
        </motion.aside>
      )}
    </AnimatePresence>
  );
};
