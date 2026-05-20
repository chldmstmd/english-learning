import { create } from "zustand";

interface SidebarStore {
  isOpen: boolean;
  word: string | null;
  lemma: string | null;
  articleId: string | null;
  sourceSentence: string | null;

  open: (word: string, lemma: string, articleId: string, sourceSentence: string) => void;
  close: () => void;
}

export const useSidebarStore = create<SidebarStore>((set) => ({
  isOpen: false,
  word: null,
  lemma: null,
  articleId: null,
  sourceSentence: null,

  open: (word, lemma, articleId, sourceSentence) =>
    set({ isOpen: true, word, lemma, articleId, sourceSentence }),

  close: () =>
    set({ isOpen: false, word: null, lemma: null, articleId: null, sourceSentence: null }),
}));
