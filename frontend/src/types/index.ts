// ── Book Types ──────────────────────────────────────────────────
export interface BookSummary {
  id: string;
  title: string;
  author: string;
  isbn: string | null;
  cover_url: string | null;
  age_range_lower: number | null;
  age_range_upper: number | null;
  question_count: number;
}

export interface BookDetail extends BookSummary {
  description: string | null;
  chapters: number;
  total_questions: number;
}

export interface BookSearchResponse {
  items: BookSummary[];
  total: number;
  page: number;
  size: number;
}

// ── Autocomplete Types ────────────────────────────────────────────
export interface AutocompleteSuggestion {
  id: string;
  title: string;
  author: string;
  cover_url: string | null;
}

export interface AutocompleteResponse {
  suggestions: AutocompleteSuggestion[];
}

// ── Quiz Types ──────────────────────────────────────────────────
export interface ChoiceResponse {
  id: string;
  text: string;
  position: number;
}

export interface QuestionResponse {
  id: string;
  question_number: number;
  question_text: string;
  chapter: number;
  chapter_title: string | null;
  choices: ChoiceResponse[];
}

export interface StartQuizResponse {
  attempt_id: string;
  questions: QuestionResponse[];
}

export interface AnswerResponse {
  is_correct: boolean;
  correct_choice_id: string;
  question_number: number;
}

export interface QuizResultItem {
  question_id: string;
  question_text: string;
  selected_choice: string;
  correct_choice: string;
  is_correct: boolean;
  chapter: number;
}

export interface CompleteQuizResponse {
  attempt_id: string;
  score: number;
  total: number;
  percentage: number;
  completed_at: string;
  results: QuizResultItem[];
}

// ── Auth Types ──────────────────────────────────────────────────
export interface UserResponse {
  id: string;
  email: string;
  display_name: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  display_name: string;
}

// ── OAuth / SSO Types ────────────────────────────────────────────
export interface OAuthProvider {
  provider: string;
  name: string;
}

export interface OAuthProvidersResponse {
  providers: OAuthProvider[];
}

export interface OAuthLink {
  provider: string;
  linked_at: string;
}

// ── Profile Types ───────────────────────────────────────────────
export interface AttemptSummary {
  attempt_number: number;
  score: number;
  total: number;
  completed_at: string;
}

export interface BookProgress {
  book_id: string;
  title: string;
  author: string;
  cover_url: string | null;
  attempts: AttemptSummary[];
  best_score: number;
  total_questions_answered: number;
  remaining_questions: number;
}

export interface UserProfile {
  id: string;
  email: string;
  display_name: string;
  avatar_url: string | null;
  has_password: boolean;
  total_quizzes: number;
  total_questions_answered: number;
  books: BookProgress[];
}
