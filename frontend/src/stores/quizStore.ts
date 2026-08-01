import { create } from 'zustand';
import type { QuestionResponse, QuizResultItem } from '../types';

type QuizPhase = 'idle' | 'in-progress' | 'complete';

interface QuizState {
  phase: QuizPhase;
  attemptId: string | null;
  questions: QuestionResponse[];
  currentIndex: number;
  answers: Array<{ questionId: string; choiceId: string; isCorrect: boolean }>;
  results: QuizResultItem[] | null;
  startQuiz: (attemptId: string, questions: QuestionResponse[]) => void;
  answerQuestion: (questionId: string, choiceId: string, isCorrect: boolean) => void;
  nextQuestion: () => void;
  completeQuiz: (results: QuizResultItem[]) => void;
  reset: () => void;
}

export const useQuizStore = create<QuizState>((set, get) => ({
  phase: 'idle',
  attemptId: null,
  questions: [],
  currentIndex: 0,
  answers: [],
  results: null,

  startQuiz: (attemptId, questions) =>
    set({ phase: 'in-progress', attemptId, questions, currentIndex: 0, answers: [], results: null }),

  answerQuestion: (questionId, choiceId, isCorrect) => {
    const { answers, currentIndex, questions } = get();
    const newAnswers = [...answers, { questionId, choiceId, isCorrect }];
    const isLast = currentIndex >= questions.length - 1;
    set({
      answers: newAnswers,
      phase: isLast ? 'complete' : 'in-progress',
    });
  },

  nextQuestion: () => {
    const { currentIndex, questions } = get();
    if (currentIndex < questions.length - 1) {
      set({ currentIndex: currentIndex + 1 });
    }
  },

  completeQuiz: (results) => set({ phase: 'complete', results }),

  reset: () =>
    set({ phase: 'idle', attemptId: null, questions: [], currentIndex: 0, answers: [], results: null }),
}));
