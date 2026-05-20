import { create } from "zustand";
import type { Annotation, WordStatus } from "../types";

interface VocabStore {
  wordStatuses: Record<string, WordStatus>;
  articleAnnotations: Record<string, Record<string, Annotation>>;

  getStatus: (lemma: string) => WordStatus;
  getAnnotation: (articleId: string, lemma: string) => Annotation | undefined;
  setWordStatus: (lemma: string, status: WordStatus) => void;
  setAnnotation: (articleId: string, lemma: string, annotation: Annotation) => void;
  initFromArticle: (
    articleId: string,
    wordStatuses: Record<string, WordStatus>,
    annotations: Record<string, Annotation>
  ) => void;
  mergeAnnotations: (articleId: string, annotations: Record<string, Annotation>) => void;
}

export const useVocabStore = create<VocabStore>((set, get) => ({
  wordStatuses: {},
  articleAnnotations: {},

  getStatus: (lemma) => get().wordStatuses[lemma] ?? "unseen",

  getAnnotation: (articleId, lemma) => get().articleAnnotations[articleId]?.[lemma],

  setWordStatus: (lemma, status) =>
    set((s) => ({ wordStatuses: { ...s.wordStatuses, [lemma]: status } })),

  setAnnotation: (articleId, lemma, annotation) =>
    set((s) => ({
      articleAnnotations: {
        ...s.articleAnnotations,
        [articleId]: { ...(s.articleAnnotations[articleId] ?? {}), [lemma]: annotation },
      },
    })),

  initFromArticle: (articleId, wordStatuses, annotations) =>
    set((s) => ({
      wordStatuses: { ...s.wordStatuses, ...wordStatuses },
      articleAnnotations: { ...s.articleAnnotations, [articleId]: annotations },
    })),

  mergeAnnotations: (articleId, annotations) =>
    set((s) => ({
      articleAnnotations: {
        ...s.articleAnnotations,
        [articleId]: { ...(s.articleAnnotations[articleId] ?? {}), ...annotations },
      },
    })),
}));
