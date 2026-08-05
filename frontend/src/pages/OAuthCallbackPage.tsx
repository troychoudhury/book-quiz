import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import api from '../services/api';
import { useAuthStore } from '../stores/authStore';
import type { UserProfile } from '../types';

/**
 * SSO callback page — receives the app's JWTs in the URL fragment
 * (never in the query string) after the backend completes the OAuth
 * exchange, stores them, and redirects to the app.
 *
 * See issues/book-quiz-tfx.md §2.2 (fragment delivery) and B1 (CSP).
 */
export default function OAuthCallbackPage() {
  const { setTokens, setUser } = useAuthStore();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // The fragment is not sent to the server; still, don't leave tokens
    // lingering in the URL bar after we've read them.
    const hash = window.location.hash.slice(1);
    window.history.replaceState(null, '', window.location.pathname + window.location.search);

    const queryError = new URLSearchParams(window.location.search).get('error');
    if (queryError) {
      setError(`Sign-in failed: ${queryError}. Please try again.`);
      return;
    }

    const params = new URLSearchParams(hash);
    const accessToken = params.get('access_token');
    const refreshToken = params.get('refresh_token');
    const redirectTo = params.get('redirect_to');
    const destination =
      redirectTo && redirectTo.startsWith('/') && !redirectTo.startsWith('//') ? redirectTo : '/';

    if (!accessToken || !refreshToken) {
      // Link-account flow (no tokens) — land on the profile page.
      navigate('/profile', { replace: true });
      return;
    }

    setTokens(accessToken, refreshToken);

    // Populate the auth store with the real profile (name/avatar) so the UI
    // never shows a placeholder identity.
    api
      .get<UserProfile>('/api/v1/users/me/profile')
      .then(({ data }) => {
        setUser({
          id: data.id,
          email: data.email,
          display_name: data.display_name,
          avatar_url: data.avatar_url,
          hasPassword: data.has_password,
        });
      })
      .catch(() => {
        setUser({ id: '', email: '', display_name: '' });
      })
      .finally(() => navigate(destination, { replace: true }));
  }, [navigate, setTokens, setUser]);

  return (
    <main className="min-h-[70vh] flex items-center justify-center px-4">
      <div className="bg-white rounded-xl shadow-sm p-8 w-full max-w-md text-center">
        {error ? (
          <>
            <h1 className="text-xl font-bold mb-2">Sign-in failed</h1>
            <p className="text-sm text-red-600 mb-4" role="alert">
              {error}
            </p>
            <Link to="/login" className="text-blue-600 text-sm hover:underline">
              Back to login
            </Link>
          </>
        ) : (
          <p className="text-gray-600">Completing sign-in…</p>
        )}
      </div>
    </main>
  );
}
