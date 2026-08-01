import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

export default function LandingPage() {
  const [query, setQuery] = useState('');
  const navigate = useNavigate();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      navigate(`/search?q=${encodeURIComponent(query.trim())}`);
    }
  };

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-4 bg-gradient-to-b from-blue-50 to-white">
      <div className="text-center max-w-2xl">
        <h1 className="text-5xl font-bold text-gray-900 mb-4">
          Test Your Reading Comprehension
        </h1>
        <p className="text-xl text-gray-600 mb-8">
          Search for a book, take an AI-generated quiz, and discover how well you really understood it.
        </p>

        <form onSubmit={handleSearch} className="w-full max-w-xl mx-auto">
          <div className="relative">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by book title or ISBN..."
              className="w-full px-6 py-4 text-lg border-2 border-gray-300 rounded-full focus:border-blue-500 focus:outline-none shadow-sm"
              aria-label="Search for a book"
            />
            <button
              type="submit"
              className="absolute right-2 top-1/2 -translate-y-1/2 bg-blue-600 text-white px-6 py-2 rounded-full hover:bg-blue-700 transition"
            >
              Search
            </button>
          </div>
        </form>

        <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="p-6 bg-white rounded-xl shadow-sm">
            <div className="text-3xl mb-3">🔍</div>
            <h3 className="font-semibold text-lg mb-2">1. Search</h3>
            <p className="text-gray-600">Find any book by title or ISBN from our curated collection.</p>
          </div>
          <div className="p-6 bg-white rounded-xl shadow-sm">
            <div className="text-3xl mb-3">📝</div>
            <h3 className="font-semibold text-lg mb-2">2. Take a Quiz</h3>
            <p className="text-gray-600">Answer 10 AI-generated questions that test memory, comprehension, and interpretation.</p>
          </div>
          <div className="p-6 bg-white rounded-xl shadow-sm">
            <div className="text-3xl mb-3">📊</div>
            <h3 className="font-semibold text-lg mb-2">3. Track Progress</h3>
            <p className="text-gray-600">See your scores, retake quizzes, and watch your reading comprehension grow.</p>
          </div>
        </div>
      </div>
    </main>
  );
}
