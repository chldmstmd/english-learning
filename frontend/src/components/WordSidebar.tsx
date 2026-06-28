import React, { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X, Volume2 } from "lucide-react";
import { useSidebarStore } from "../store/sidebarStore";

function speak(text: string) {
  if ("speechSynthesis" in window) {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "en-US";
    window.speechSynthesis.speak(utterance);
  }
}

export const WordSidebar: React.FC = () => {
  const { isOpen, word, lemma, sourceSentence, translation, close } = useSidebarStore();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [close]);

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
              {lemma && lemma !== word && <span className="text-sm text-gray-400">{lemma}</span>}
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
            <div className="bg-gray-50 border border-gray-100 rounded-lg p-4">
              <p className="text-xs text-gray-500 mb-1 uppercase tracking-wide">Context translation</p>
              <p className="text-lg font-semibold text-gray-900">
                {translation ?? "翻译完成后显示结果"}
              </p>
            </div>

            {sourceSentence && (
              <section>
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
                  Source sentence
                </h3>
                <p className="text-sm leading-6 text-gray-700">{sourceSentence}</p>
              </section>
            )}
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
};
