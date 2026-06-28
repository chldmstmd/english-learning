import { create } from "zustand";

interface SidebarStore {
  isOpen: boolean;
  word: string | null;
  lemma: string | null;
  articleId: string | null;
  sourceSentence: string | null;
  translation: string | null;

  open: (
    word: string,
    lemma: string,
    articleId: string,
    sourceSentence: string,
    translation?: string | null
  ) => void;
  close: () => void;
}

export const useSidebarStore = create<SidebarStore>((set) => ({
  isOpen: false,
  word: null,
  lemma: null,
  articleId: null,
  sourceSentence: null,
  translation: null,

  open: (word, lemma, articleId, sourceSentence, translation = null) =>
    set({ isOpen: true, word, lemma, articleId, sourceSentence, translation }),

  close: () =>
    set({
      isOpen: false,
      word: null,
      lemma: null,
      articleId: null,
      sourceSentence: null,
      translation: null,
    }),
}));
