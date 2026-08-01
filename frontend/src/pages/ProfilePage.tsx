import { useAuthStore } from '../stores/authStore';

export default function ProfilePage() {
  const { user, isAuthenticated } = useAuthStore();

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

  return (
    <main className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-4xl mx-auto">
        <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
          <h1 className="text-3xl font-bold mb-2">Welcome, {user.display_name}!</h1>
          <p className="text-gray-600">{user.email}</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-white rounded-xl shadow-sm p-6 text-center">
            <div className="text-3xl font-bold text-blue-600">0</div>
            <div className="text-gray-600">Quizzes Completed</div>
          </div>
          <div className="bg-white rounded-xl shadow-sm p-6 text-center">
            <div className="text-3xl font-bold text-green-600">0</div>
            <div className="text-gray-600">Questions Answered</div>
          </div>
          <div className="bg-white rounded-xl shadow-sm p-6 text-center">
            <div className="text-3xl font-bold text-purple-600">-</div>
            <div className="text-gray-600">Best Score</div>
          </div>
        </div>

        <h2 className="text-2xl font-bold mb-4">Your Books</h2>
        <div className="bg-white rounded-xl shadow-sm p-6">
          <p className="text-gray-500 text-center py-8">
            No books completed yet. Search for a book and take your first quiz!
          </p>
        </div>
      </div>
    </main>
  );
}
