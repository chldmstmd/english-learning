import { create } from "zustand";
import type { Annotation } from "../types";

export const annotationKey = (
  articleParagraphId: string,
  sentenceIndex: number,
  wordIndex: number
) => `${articleParagraphId}-${sentenceIndex}-${wordIndex}`;

interface AnnotationStore {
  articleAnnotations: Record<string, Record<string, Annotation>>;

  getAnnotation: (
    articleId: string,
    articleParagraphId: string,
    sentenceIndex: number,
    wordIndex: number
  ) => Annotation | undefined;
  setAnnotation: (
    articleId: string,
    articleParagraphId: string,
    sentenceIndex: number,
    wordIndex: number,
    annotation: Annotation
  ) => void;
  initFromArticle: (articleId: string, annotations: Record<string, Annotation>) => void;
}

export const useAnnotationStore = create<AnnotationStore>((set, get) => ({
  articleAnnotations: {},

  getAnnotation: (articleId, articleParagraphId, sentenceIndex, wordIndex) =>
    get().articleAnnotations[articleId]?.[
      annotationKey(articleParagraphId, sentenceIndex, wordIndex)
    ],

  setAnnotation: (articleId, articleParagraphId, sentenceIndex, wordIndex, annotation) =>
    set((s) => ({
      articleAnnotations: {
        ...s.articleAnnotations,
        [articleId]: {
          ...(s.articleAnnotations[articleId] ?? {}),
          [annotationKey(articleParagraphId, sentenceIndex, wordIndex)]: annotation,
        },
      },
    })),

  initFromArticle: (articleId, annotations) =>
    set((s) => ({
      articleAnnotations: { ...s.articleAnnotations, [articleId]: annotations },
    })),
}));
