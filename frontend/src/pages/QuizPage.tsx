import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { quizApi } from '../services/api';
import { useQuizStore } from '../stores/quizStore';
import type { ChoiceResponse } from '../types';

export default function QuizPage() {
  const { attemptId } = useParams<{ attemptId: string }>();
  const navigate = useNavigate();
  const {
    phase, questions, currentIndex, startQuiz, answerQuestion,
    nextQuestion, completeQuiz, results,
  } = useQuizStore();
  const [selectedChoice, setSelectedChoice] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ isCorrect: boolean; correctId: string } | null>(null);
  const [email, setEmail] = useState('');

  const currentQuestion = questions[currentIndex];
  const progress = questions.length > 0 ? ((currentIndex + 1) / questions.length) * 100 : 0;

  const handleChoiceSelect = async (choice: ChoiceResponse) => {
    if (selectedChoice || !attemptId) return;
    setSelectedChoice(choice.id);

    try {
      const { data } = await quizApi.answer(attemptId, currentQuestion.id, choice.id);
      setFeedback({ isCorrect: data.is_correct, correctId: data.correct_choice_id });
      answerQuestion(currentQuestion.id, choice.id, data.is_correct);
    } catch (err) {
      console.error('Failed to submit answer:', err);
    }
  };

  const handleNext = () => {
    setSelectedChoice(null);
    setFeedback(null);
    if (currentIndex >= questions.length - 1) {
      handleComplete();
    } else {
      nextQuestion();
    }
  };

  const handleComplete = async () => {
    if (!attemptId) return;
    try {
      const { data } = await quizApi.complete(attemptId, email || undefined);
      completeQuiz(data.results);
      navigate(`/quiz/${attemptId}/complete`);
    } catch (err) {
      console.error('Failed to complete quiz:', err);
    }
  };

  if (phase === 'idle') {
    return <div className="flex items-center justify-center min-h-screen">Loading quiz...</div>;
  }

  if (phase === 'complete' && results) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="bg-white p-8 rounded-xl shadow-lg max-w-md w-full text-center">
          <h2 className="text-2xl font-bold mb-4">Quiz Complete!</h2>
          <p className="text-lg">Redirecting to results...</p>
        </div>
      </div>
    );
  }

  if (!currentQuestion) return null;

  return (
    <main className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-2xl mx-auto">
        {/* Progress bar */}
        <div className="mb-6">
          <div className="flex justify-between text-sm text-gray-600 mb-2">
            <span>Question {currentIndex + 1} of {questions.length}</span>
            <span>{Math.round(progress)}%</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* Question card */}
        <div className="bg-white rounded-xl shadow-sm p-6 mb-4">
          <span className="text-sm text-gray-500">
            Chapter {currentQuestion.chapter}{currentQuestion.chapter_title ? `: ${currentQuestion.chapter_title}` : ''}
          </span>
          <h2 className="text-xl font-semibold mt-2 mb-6">{currentQuestion.question_text}</h2>

          <div className="space-y-3">
            {currentQuestion.choices.map((choice) => {
              let buttonClass = 'w-full text-left p-4 rounded-lg border-2 transition ';
              if (!selectedChoice) {
                buttonClass += 'border-gray-200 hover:border-blue-400 hover:bg-blue-50 cursor-pointer';
              } else if (feedback) {
                if (choice.id === feedback.correctId) {
                  buttonClass += 'border-green-500 bg-green-50';
                } else if (choice.id === selectedChoice && !feedback.isCorrect) {
                  buttonClass += 'border-red-500 bg-red-50';
                } else {
                  buttonClass += 'border-gray-200 opacity-50';
                }
              } else {
                buttonClass += choice.id === selectedChoice
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200';
              }

              return (
                <button
                  key={choice.id}
                  onClick={() => handleChoiceSelect(choice)}
                  disabled={!!selectedChoice}
                  className={buttonClass}
                >
                  <span className="font-medium">{String.fromCharCode(65 + choice.position)}.</span>{' '}
                  {choice.text}
                </button>
              );
            })}
          </div>

          {/* Feedback */}
          {feedback && (
            <div className={`mt-4 p-4 rounded-lg ${feedback.isCorrect ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
              {feedback.isCorrect ? '✅ Correct!' : '❌ Incorrect.'}
            </div>
          )}
        </div>

        {/* Next button */}
        {selectedChoice && (
          <button
            onClick={handleNext}
            className="w-full bg-blue-600 text-white py-3 rounded-lg font-medium hover:bg-blue-700 transition"
          >
            {currentIndex >= questions.length - 1 ? 'Finish Quiz' : 'Next Question'}
          </button>
        )}

        {/* Guest email capture (shown when completing) */}
        {currentIndex >= questions.length - 1 && selectedChoice && (
          <div className="mt-4">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Enter your email to receive results (optional)"
              className="w-full px-4 py-2 border border-gray-300 rounded-lg"
            />
          </div>
        )}
      </div>
    </main>
  );
}
