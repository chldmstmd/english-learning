import React from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import { useVocabStore } from "../store/vocabStore";
import { useSidebarStore } from "../store/sidebarStore";
import { cn } from "../utils/cn";
import type { Token, Sentence, TranslateResponse } from "../types";

// Single highlight for an in-progress vocab word (new/reviewing); mastered & unseen are unstyled.
const VOCAB_HIGHLIGHT =
  "underline decoration-amber-400 decoration-dashed underline-offset-4 cursor-pointer";

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
  const annotation = getAnnotation(articleId, token.sentence_index, token.index);

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
            sentence_index: token.sentence_index,
            word_index: token.index,
          },
        })
        .json<TranslateResponse>(),
    onMutate: () => {
      // optimistic highlight only for brand-new words; never downgrade an
      // already-tracked word (reviewing/mastered) to "new" on click.
      if (getStatus(token.lemma) === "unseen") {
        setWordStatus(token.lemma, "new");
      }
    },
    onSuccess: (data) => {
      setWordStatus(token.lemma, data.status);
      setAnnotation(articleId, token.sentence_index, token.index, {
        translation: data.translation,
        source_sentence: getSentenceText(),
        is_fallback: data.is_fallback,
        gen_status: "done",
      });
    },
    onError: () => {
      // roll back optimistic highlight only if nothing else marked it
      if (getStatus(token.lemma) === "new" && !getAnnotation(articleId, token.sentence_index, token.index)) {
        setWordStatus(token.lemma, "unseen");
      }
    },
  });

  const showTranslation = !!annotation?.translation;
  // highlight = word is in vocab and not yet mastered
  const highlighted = status === "new" || status === "reviewing";

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (showTranslation) {
      // already translated here -> manage the word
      openSidebar(token.text, token.lemma, articleId, getSentenceText());
    } else {
      translateMutation.mutate();
      if (autoOpenSidebar) {
        openSidebar(token.text, token.lemma, articleId, getSentenceText());
      }
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
          highlighted && VOCAB_HIGHLIGHT
        )}
        onClick={handleClick}
        data-word={token.lemma}
        data-status={status}
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
