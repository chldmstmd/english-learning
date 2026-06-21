import { create } from "zustand";
import type { Annotation, WordStatus } from "../types";

export const annotationKey = (sentenceIndex: number, wordIndex: number) =>
  `${sentenceIndex}-${wordIndex}`;

interface VocabStore {
  wordStatuses: Record<string, WordStatus>;
  articleAnnotations: Record<string, Record<string, Annotation>>;

  getStatus: (lemma: string) => WordStatus;
  getAnnotation: (articleId: string, sentenceIndex: number, wordIndex: number) => Annotation | undefined;
  setWordStatus: (lemma: string, status: WordStatus) => void;
  setAnnotation: (articleId: string, sentenceIndex: number, wordIndex: number, annotation: Annotation) => void;
  initFromArticle: (
    articleId: string,
    wordStatuses: Record<string, WordStatus>,
    annotations: Record<string, Annotation>
  ) => void;
}

export const useVocabStore = create<VocabStore>((set, get) => ({
  wordStatuses: {},
  articleAnnotations: {},

  getStatus: (lemma) => get().wordStatuses[lemma] ?? "unseen",

  getAnnotation: (articleId, sentenceIndex, wordIndex) =>
    get().articleAnnotations[articleId]?.[annotationKey(sentenceIndex, wordIndex)],

  setWordStatus: (lemma, status) =>
    set((s) => ({ wordStatuses: { ...s.wordStatuses, [lemma]: status } })),

  setAnnotation: (articleId, sentenceIndex, wordIndex, annotation) =>
    set((s) => ({
      articleAnnotations: {
        ...s.articleAnnotations,
        [articleId]: {
          ...(s.articleAnnotations[articleId] ?? {}),
          [annotationKey(sentenceIndex, wordIndex)]: annotation,
        },
      },
    })),

  initFromArticle: (articleId, wordStatuses, annotations) =>
    set((s) => ({
      wordStatuses: { ...s.wordStatuses, ...wordStatuses },
      articleAnnotations: { ...s.articleAnnotations, [articleId]: annotations },
    })),
}));
