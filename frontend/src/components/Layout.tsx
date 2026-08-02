import { useState } from 'react';
import { Link, Outlet, useNavigate } from 'react-router-dom';

import { useAuthStore } from '../stores/authStore';

/**
 * App layout with a persistent header: logo, search bar, and auth controls.
 * Wraps routed page content via <Outlet />.
 */
export default function Layout() {
  const { isAuthenticated, user, logout } = useAuthStore();
  const [query, setQuery] = useState('');
  const navigate = useNavigate();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (trimmed) {
      navigate(`/search?q=${encodeURIComponent(trimmed)}`);
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 h-16 flex items-center gap-4">
          <Link to="/" className="text-xl font-bold text-blue-600 whitespace-nowrap">
            📚 Book Quiz
          </Link>

          <form onSubmit={handleSearch} className="flex-1 max-w-md" role="search">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search books..."
              aria-label="Search books"
              className="w-full px-4 py-2 border border-gray-300 rounded-full text-sm focus:border-blue-500 focus:outline-none"
            />
          </form>

          <nav className="ml-auto flex items-center gap-3">
            {isAuthenticated && user ? (
              <>
                <Link
                  to="/profile"
                  className="text-sm font-medium text-gray-700 hover:text-blue-600"
                >
                  {user.display_name}
                </Link>
                <button
                  onClick={handleLogout}
                  className="text-sm px-4 py-2 rounded-full border border-gray-300 hover:bg-gray-50"
                >
                  Log out
                </button>
              </>
            ) : (
              <>
                <Link
                  to="/login"
                  className="text-sm px-4 py-2 rounded-full border border-gray-300 hover:bg-gray-50"
                >
                  Log in
                </Link>
                <Link
                  to="/signup"
                  className="text-sm px-4 py-2 rounded-full bg-blue-600 text-white hover:bg-blue-700"
                >
                  Sign up
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="bg-white border-t border-gray-200 py-4 text-center text-sm text-gray-500">
        Book Quiz — test your reading comprehension
      </footer>
    </div>
  );
}
