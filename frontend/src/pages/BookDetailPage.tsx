import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { booksApi, quizApi } from '../services/api';
import { useQuizStore } from '../stores/quizStore';

export default function BookDetailPage() {
  const { bookId } = useParams<{ bookId: string }>();
  const navigate = useNavigate();
  const startQuiz = useQuizStore((s) => s.startQuiz);

  const {
    data: book,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['book', bookId],
    queryFn: () => booksApi.getById(bookId!).then((res) => res.data),
    enabled: !!bookId,
  });

  const handleStartQuiz = async () => {
    if (!bookId) return;
    try {
      const { data } = await quizApi.start(bookId);
      startQuiz(data.attempt_id, data.questions);
      navigate(`/quiz/${data.attempt_id}`);
    } catch (err) {
      console.error('Failed to start quiz:', err);
    }
  };

  if (isLoading) {
    return <p className="text-center py-16 text-gray-500">Loading book...</p>;
  }

  if (isError || !book) {
    return (
      <main className="max-w-2xl mx-auto px-4 py-16 text-center">
        <h1 className="text-2xl font-bold mb-4">Book not found</h1>
        <Link to="/" className="text-blue-600 hover:underline">
          Back to search
        </Link>
      </main>
    );
  }

  return (
    <main className="max-w-3xl mx-auto px-4 py-8">
      <div className="bg-white rounded-xl shadow-sm p-6 flex gap-6">
        <div className="w-32 h-48 bg-gray-100 rounded flex-shrink-0 overflow-hidden">
          {book.cover_url ? (
            <img src={book.cover_url} alt="" className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-5xl">📖</div>
          )}
        </div>
        <div className="flex-1">
          <h1 className="text-3xl font-bold">{book.title}</h1>
          <p className="text-gray-600 mt-1">{book.author}</p>
          {book.isbn && <p className="text-xs text-gray-400 mt-2">ISBN: {book.isbn}</p>}
          {book.age_range_lower && book.age_range_upper && (
            <p className="text-sm text-gray-500 mt-1">
              Ages {book.age_range_lower}–{book.age_range_upper}
            </p>
          )}
          <div className="mt-4 flex items-center gap-4 text-sm text-gray-600">
            <span>{book.chapters} chapters</span>
            <span>{book.total_questions} questions</span>
          </div>
          <button
            onClick={handleStartQuiz}
            disabled={book.total_questions === 0}
            className="mt-6 px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {book.total_questions === 0 ? 'Quiz coming soon' : 'Start Quiz'}
          </button>
        </div>
      </div>

      {book.description && (
        <div className="bg-white rounded-xl shadow-sm p-6 mt-6">
          <h2 className="font-semibold mb-2">About this book</h2>
          <p className="text-gray-700 leading-relaxed">{book.description}</p>
        </div>
      )}
    </main>
  );
}
