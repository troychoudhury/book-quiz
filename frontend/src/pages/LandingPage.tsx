import SearchBar from '../components/SearchBar';

export default function LandingPage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-4 bg-gradient-to-b from-blue-50 to-white">
      <div className="text-center max-w-2xl">
        <h1 className="text-5xl font-bold text-gray-900 mb-4">Test Your Reading Comprehension</h1>
        <p className="text-xl text-gray-600 mb-8">
          Search for a book, take an AI-generated quiz, and discover how well you really understood
          it.
        </p>

        <SearchBar variant="hero" autoFocus />

        <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="p-6 bg-white rounded-xl shadow-sm">
            <div className="text-3xl mb-3">🔍</div>
            <h3 className="font-semibold text-lg mb-2">1. Search</h3>
            <p className="text-gray-600">
              Find any book by title or ISBN from our curated collection.
            </p>
          </div>
          <div className="p-6 bg-white rounded-xl shadow-sm">
            <div className="text-3xl mb-3">📝</div>
            <h3 className="font-semibold text-lg mb-2">2. Take a Quiz</h3>
            <p className="text-gray-600">
              Answer 10 AI-generated questions that test memory, comprehension, and interpretation.
            </p>
          </div>
          <div className="p-6 bg-white rounded-xl shadow-sm">
            <div className="text-3xl mb-3">📊</div>
            <h3 className="font-semibold text-lg mb-2">3. Track Progress</h3>
            <p className="text-gray-600">
              See your scores, retake quizzes, and watch your reading comprehension grow.
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}
