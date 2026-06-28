import { create } from "zustand";
import type { Annotation } from "../types";

export const annotationKey = (sentenceIndex: number, wordIndex: number) =>
  `${sentenceIndex}-${wordIndex}`;

interface AnnotationStore {
  articleAnnotations: Record<string, Record<string, Annotation>>;

  getAnnotation: (
    articleId: string,
    sentenceIndex: number,
    wordIndex: number
  ) => Annotation | undefined;
  setAnnotation: (
    articleId: string,
    sentenceIndex: number,
    wordIndex: number,
    annotation: Annotation
  ) => void;
  initFromArticle: (articleId: string, annotations: Record<string, Annotation>) => void;
}

export const useAnnotationStore = create<AnnotationStore>((set, get) => ({
  articleAnnotations: {},

  getAnnotation: (articleId, sentenceIndex, wordIndex) =>
    get().articleAnnotations[articleId]?.[annotationKey(sentenceIndex, wordIndex)],

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

  initFromArticle: (articleId, annotations) =>
    set((s) => ({
      articleAnnotations: { ...s.articleAnnotations, [articleId]: annotations },
    })),
}));
