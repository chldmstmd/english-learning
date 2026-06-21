export type WordStatus = "unseen" | "new" | "reviewing" | "mastered";

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
  is_library?: boolean;
  source_category?: string | null;
  difficulty?: Difficulty | null;
  translation_status?: TranslationStatus;
}

export interface ArticleDetail {
  id: string;
  title: string;
  tokens: Token[];
  sentences: Sentence[];
  word_count: number;
  annotations: Record<string, Annotation>;
  word_statuses: Record<string, WordStatus>;
  // Library metadata (present for library articles)
  is_library?: boolean;
  is_bookmarked?: boolean;
  source_url?: string | null;
  source_category?: string | null;
  difficulty?: "level1" | "level2" | null;
  published_at?: string | null;
  translation_status?: TranslationStatus;
  book_id?: string | null;
  chapter_order?: number | null;
  prev_article_id?: string | null;
  next_article_id?: string | null;
  last_sentence_index?: number | null;
}

export interface BookListItem {
  id: string;
  title: string;
  cover_image_url: string | null;
  source_category: string | null;
  created_at: string;
  chapter_count: number;
  read_chapter_order: number | null;
  is_from_library: boolean;
}

export interface ChapterListItem {
  id: string;
  title: string;
  chapter_order: number;
  word_count: number;
  last_sentence_index: number | null;
  translation_status: TranslationStatus;
}

export interface BookDetail {
  id: string;
  title: string;
  cover_image_url: string | null;
  source_category: string | null;
  created_at: string;
  chapters: ChapterListItem[];
  continue_article_id: string | null;
  continue_sentence_index: number | null;
}

export interface LibraryBookListItem {
  id: string;
  title: string;
  cover_image_url: string | null;
  source_category: string | null;
  created_at: string;
  chapter_count: number;
  is_saved: boolean;
}

export type Difficulty = "level1" | "level2";
export type TranslationStatus = "untranslated" | "processing" | "done" | "stale" | "failed";

export interface LibraryArticleListItem {
  id: string;
  title: string;
  word_count: number;
  source_category: string | null;
  difficulty: Difficulty | null;
  published_at: string | null;
  cover_image_url: string | null;
  source_url: string | null;
  translation_status: TranslationStatus;
  raw_text: string;
  created_at: string;
  is_bookmarked: boolean;
  read_at: string | null;
}

export interface VocabItem {
  id: string;
  word: string;
  pos: string | null;
  context_translation: string | null;
  status: WordStatus;
  created_at: string;
  mastered_at: string | null;
  updated_at: string;
}

export interface VocabLocation {
  article_id: string;
  article_title: string;
  is_library: boolean;
  sentence_index: number;
  source_sentence: string | null;
  is_stale: boolean;
}

export interface VocabDetail {
  word: string;
  phonetic: string | null;
  status: WordStatus;
  context_translation: string | null;
  source_sentence: string | null;
  definitions: Array<{
    pos: string;
    definition: string;
    example: string;
  }>;
  locations: VocabLocation[];
}

export interface TranslateResponse {
  word: string;
  lemma: string;
  translation: string;
  is_fallback: boolean;
  status: WordStatus;
}

export interface AppSettings {
  use_free_translation_fallback: boolean;
  auto_open_sidebar_on_mark: boolean;
}

export interface AuthUser {
  id: string;
  email: string;
  role: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}
