import { Link } from 'react-router-dom';

import { useQuizStore } from '../stores/quizStore';

export default function QuizCompletePage() {
  const { results, answers, questions } = useQuizStore();

  const score = answers.filter((a) => a.isCorrect).length;
  const total = questions.length || answers.length || 0;
  const percentage = total > 0 ? Math.round((score / total) * 100) : 0;

  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      <div className="bg-white rounded-xl shadow-sm p-8 text-center">
        <h1 className="text-3xl font-bold mb-2">Quiz Complete!</h1>
        <div className="text-5xl font-bold text-blue-600 my-4">{percentage}%</div>
        <p className="text-gray-600">
          You answered {score} of {total} questions correctly.
        </p>

        <div className="flex gap-4 justify-center mt-6">
          <Link
            to="/"
            className="px-5 py-2 rounded-full border border-gray-300 hover:bg-gray-50 text-sm"
          >
            Back to books
          </Link>
          <Link
            to="/profile"
            className="px-5 py-2 rounded-full bg-blue-600 text-white hover:bg-blue-700 text-sm"
          >
            View my profile
          </Link>
        </div>
      </div>

      {results && results.length > 0 && (
        <div className="mt-8 space-y-3">
          <h2 className="text-xl font-bold">Answer breakdown</h2>
          {results.map((r, i) => (
            <div
              key={r.question_id}
              className={`bg-white rounded-xl shadow-sm p-4 border-l-4 ${
                r.is_correct ? 'border-green-500' : 'border-red-500'
              }`}
            >
              <p className="text-sm text-gray-500 mb-1">
                Question {i + 1} · Chapter {r.chapter}
              </p>
              <p className="font-medium">{r.question_text}</p>
              <div className="mt-2 text-sm">
                <p className={r.is_correct ? 'text-green-700' : 'text-red-700'}>
                  Your answer: {r.selected_choice}
                </p>
                {!r.is_correct && (
                  <p className="text-green-700">Correct answer: {r.correct_choice}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
