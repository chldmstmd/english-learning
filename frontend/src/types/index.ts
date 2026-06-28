export interface Token {
  text: string;
  pos: string;
  lemma: string;
  index: number;
  sentence_index: number;
  is_punct: boolean;
  is_alpha: boolean;
  ws: string;
}

export interface Sentence {
  index: number;
  text: string;
}

export interface Annotation {
  translation: string | null;
  source_sentence: string | null;
  is_fallback: boolean;
  gen_status: "pending" | "done" | "failed";
  is_stale?: boolean;
}

export interface ArticleListItem {
  id: string;
  title: string;
  word_count: number;
  created_at: string;
  translation_status?: TranslationStatus;
  translation_progress: TranslationProgress;
}

export interface ArticleDetail {
  id: string;
  title: string;
  tokens: Token[];
  sentences: Sentence[];
  word_count: number;
  annotations: Record<string, Annotation>;
  translation_status?: TranslationStatus;
  translation_progress: TranslationProgress;
  last_sentence_index?: number | null;
}

export type TranslationStatus = "untranslated" | "processing" | "done" | "stale" | "failed";

export interface TranslationProgress {
  total_words: number;
  processed_words: number;
  total_chunks: number;
  completed_chunks: number;
  percent: number;
}

export interface ArticleTranslateResponse {
  translation_status: TranslationStatus;
  translation_progress: TranslationProgress;
}

export interface TranslateResponse {
  word: string;
  lemma: string;
  translation: string;
  is_fallback: boolean;
}

export interface AppSettings {
  use_free_translation_fallback: boolean;
  auto_open_sidebar_on_mark: boolean;
}

export interface AuthUser {
  id: string;
  email: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}
