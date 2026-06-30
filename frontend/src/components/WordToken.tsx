import React from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import { useAnnotationStore } from "../store/annotationStore";
import { useSidebarStore } from "../store/sidebarStore";
import { cn } from "../utils/cn";
import type { Token, Sentence, TranslateResponse } from "../types";

const TRANSLATION_HIGHLIGHT =
  "underline decoration-amber-400 decoration-dashed underline-offset-4 cursor-pointer";

interface Props {
  token: Token;
  articleId: string;
  articleParagraphId: string;
  sentences: Sentence[];
  autoOpenSidebar: boolean;
}

export const WordToken: React.FC<Props> = ({
  token,
  articleId,
  articleParagraphId,
  sentences,
  autoOpenSidebar,
}) => {
  const { getAnnotation, setAnnotation } = useAnnotationStore();
  const { open: openSidebar } = useSidebarStore();

  const annotation = getAnnotation(articleId, articleParagraphId, token.sentence_index, token.index);

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
            article_paragraph_id: articleParagraphId,
            sentence_index: token.sentence_index,
            word_index: token.index,
          },
        })
        .json<TranslateResponse>(),
    onSuccess: (data) => {
      setAnnotation(articleId, articleParagraphId, token.sentence_index, token.index, {
        translation: data.translation,
        source_sentence: getSentenceText(),
        is_fallback: data.is_fallback,
        gen_status: "done",
      });
      if (autoOpenSidebar) {
        openSidebar(token.text, token.lemma, articleId, getSentenceText(), data.translation);
      }
    },
  });

  const showTranslation = !!annotation?.translation;
  const highlighted = showTranslation || translateMutation.isPending;

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (annotation?.translation) {
      openSidebar(token.text, token.lemma, articleId, getSentenceText(), annotation.translation);
    } else {
      translateMutation.mutate();
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

  return (
    <>
      <ruby
        className={cn(
          "cursor-pointer rounded hover:bg-gray-100 transition-colors",
          highlighted && TRANSLATION_HIGHLIGHT
        )}
        onClick={handleClick}
        data-word={token.lemma}
        aria-label={
          showTranslation ? `${token.text}, 翻译: ${annotation!.translation}` : token.text
        }
      >
        {token.text}
        {showTranslation ? (
          <rt className="text-red-500 not-italic text-[11px]">
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
