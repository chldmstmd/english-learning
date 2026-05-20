import React from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import { useVocabStore } from "../store/vocabStore";
import { useSidebarStore } from "../store/sidebarStore";
import { cn } from "../utils/cn";
import type { Token, Sentence, TranslateResponse, WordStatus } from "../types";

const STATUS_STYLES: Record<WordStatus, string> = {
  unseen:    "cursor-pointer hover:bg-gray-100 rounded transition-colors",
  new:       "text-red-600 underline decoration-red-400 decoration-solid cursor-pointer",
  reviewing: "bg-yellow-100 border-b-2 border-yellow-400 cursor-pointer",
  mastered:  "underline decoration-gray-300 decoration-dashed cursor-pointer",
};

interface Props {
  token: Token;
  articleId: string;
  sentences: Sentence[];
  autoOpenSidebar: boolean;
}

export const WordToken: React.FC<Props> = ({ token, articleId, sentences, autoOpenSidebar }) => {
  const { getStatus, getAnnotation, setWordStatus, setAnnotation } = useVocabStore();
  const { open: openSidebar } = useSidebarStore();

  const status = getStatus(token.lemma);
  const annotation = getAnnotation(articleId, token.lemma);

  const getSentenceText = () =>
    sentences.find((s) => s.index === token.sentence_index)?.text ?? "";

  const translateMutation = useMutation({
    mutationFn: () =>
      api
        .post("translate-word", {
          json: {
            word: token.text,
            lemma: token.lemma,
            sentence: getSentenceText(),
            article_id: articleId,
          },
        })
        .json<TranslateResponse>(),
    onMutate: () => {
      setWordStatus(token.lemma, "new");
    },
    onSuccess: (data) => {
      setWordStatus(token.lemma, data.status);
      setAnnotation(articleId, token.lemma, {
        translation: data.translation,
        source_sentence: getSentenceText(),
        is_fallback: data.is_fallback,
        gen_status: "done",
      });
    },
    onError: () => {
      setWordStatus(token.lemma, "unseen");
    },
  });

  const statusMutation = useMutation({
    mutationFn: (newStatus: WordStatus) =>
      api.patch(`vocab/${token.lemma}/status`, { json: { status: newStatus } }),
    onMutate: (newStatus) => {
      setWordStatus(token.lemma, newStatus);
    },
  });

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    switch (status) {
      case "unseen":
      case "mastered":
        translateMutation.mutate();
        if (autoOpenSidebar) {
          openSidebar(token.text, token.lemma, articleId, getSentenceText());
        }
        break;
      case "new":
        statusMutation.mutate("reviewing");
        break;
      case "reviewing":
        openSidebar(token.text, token.lemma, articleId, getSentenceText());
        break;
    }
  };

  // Non-clickable tokens (punctuation, numbers, etc.)
  if (token.is_punct || !token.is_alpha) {
    return (
      <>
        <span>{token.text}</span>
        {token.ws && <span>{token.ws}</span>}
      </>
    );
  }

  const showTranslation = status === "new" && !!annotation?.translation;

  return (
    <>
      <ruby
        className={cn(STATUS_STYLES[status])}
        onClick={handleClick}
        data-word={token.lemma}
        data-status={status}
        aria-label={
          showTranslation
            ? `${token.text}, 翻译: ${annotation!.translation}`
            : token.text
        }
      >
        {token.text}
        {showTranslation ? (
          <rt className="text-red-500 not-italic">
            {annotation!.translation}
            {annotation!.is_fallback && (
              <span className="text-gray-400 text-[9px] ml-0.5">*</span>
            )}
          </rt>
        ) : (
          <rt />
        )}
      </ruby>
      {token.ws && <span>{token.ws}</span>}
    </>
  );
};
