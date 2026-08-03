import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import api from '../services/api';
import type { UserProfile } from '../types';

export default function ProfilePage() {
  const { user, isAuthenticated } = useAuthStore();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isAuthenticated) {
      setLoading(false);
      return;
    }
    api
      .get<UserProfile>('/api/v1/users/me/profile')
      .then(({ data }) => setProfile(data))
      .catch(() => setProfile(null))
      .finally(() => setLoading(false));
  }, [isAuthenticated]);

  if (!isAuthenticated || !user) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <h2 className="text-2xl font-bold mb-4">Please Log In</h2>
          <p className="text-gray-600">You need to be logged in to view your profile.</p>
        </div>
      </main>
    );
  }

  if (loading) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-gray-500">Loading profile...</div>
      </main>
    );
  }

  const bestScore = profile?.books?.length
    ? Math.max(...profile.books.map((b) => b.best_score))
    : null;

  return (
    <main className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-4xl mx-auto">
        <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
          <h1 className="text-3xl font-bold mb-2">Welcome, {user.display_name}!</h1>
          <p className="text-gray-600">{user.email}</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-white rounded-xl shadow-sm p-6 text-center">
            <div className="text-3xl font-bold text-blue-600">
              {profile?.total_quizzes ?? 0}
            </div>
            <div className="text-gray-600">Quizzes Completed</div>
          </div>
          <div className="bg-white rounded-xl shadow-sm p-6 text-center">
            <div className="text-3xl font-bold text-green-600">
              {profile?.total_questions_answered ?? 0}
            </div>
            <div className="text-gray-600">Questions Answered</div>
          </div>
          <div className="bg-white rounded-xl shadow-sm p-6 text-center">
            <div className="text-3xl font-bold text-purple-600">
              {bestScore !== null ? `${bestScore}%` : '-'}
            </div>
            <div className="text-gray-600">Best Score</div>
          </div>
        </div>

        <h2 className="text-2xl font-bold mb-4">Your Books</h2>
        {profile?.books && profile.books.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {profile.books.map((book) => (
              <div
                key={book.book_id}
                className="bg-white rounded-xl shadow-sm p-6 hover:shadow-md transition"
              >
                <h3 className="font-semibold text-lg mb-1">{book.title}</h3>
                <p className="text-gray-500 text-sm mb-3">{book.author}</p>
                <div className="flex gap-4 text-sm text-gray-600 mb-3">
                  <span>Best: {book.best_score}%</span>
                  <span>{book.total_questions_answered} answered</span>
                  <span>{book.remaining_questions} remaining</span>
                </div>
                {book.attempts.length > 0 && (
                  <div className="text-xs text-gray-400 mb-3">
                    {book.attempts.length} attempt{book.attempts.length !== 1 ? 's' : ''}
                    :{' '}
                    {book.attempts.map((a) => `${a.score}/${a.total}`).join(', ')}
                  </div>
                )}
                <Link
                  to={`/books/${book.book_id}`}
                  className="inline-block text-blue-600 text-sm font-medium hover:underline"
                >
                  {book.remaining_questions > 0 ? 'Continue Quiz' : 'Retake Quiz'} →
                </Link>
              </div>
            ))}
          </div>
        ) : (
          <div className="bg-white rounded-xl shadow-sm p-6">
            <p className="text-gray-500 text-center py-8">
              No books completed yet. Search for a book and take your first quiz!
            </p>
          </div>
        )}
      </div>
    </main>
  );
}
