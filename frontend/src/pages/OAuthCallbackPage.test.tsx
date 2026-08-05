import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import api from '../services/api';
import { useAuthStore } from '../stores/authStore';
import OAuthCallbackPage from './OAuthCallbackPage';

vi.mock('../services/api', () => ({
  default: {
    get: vi.fn(),
  },
}));

function HomeProbe() {
  return <div>home-probe</div>;
}

function ProfileProbe() {
  return <div>profile-probe</div>;
}

function renderCallback(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/auth/callback" element={<OAuthCallbackPage />} />
        <Route path="/" element={<HomeProbe />} />
        <Route path="/profile" element={<ProfileProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('OAuthCallbackPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      accessToken: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,
    });
    // MemoryRouter keeps its own location — the page reads the real
    // window.location (fragment delivered by the backend redirect).
    window.history.replaceState({}, '', '/auth/callback');
  });

  it('stores tokens from the fragment and redirects home', async () => {
    window.location.hash = '#access_token=abc&refresh_token=def&token_type=bearer';
    vi.mocked(api.get).mockResolvedValue({
      data: {
        id: 'u1',
        email: 'sso@example.com',
        display_name: 'SSO User',
        avatar_url: 'https://img/a.png',
        has_password: false,
        total_quizzes: 0,
        total_questions_answered: 0,
        books: [],
      },
    } as never);

    renderCallback('/auth/callback#access_token=abc&refresh_token=def&token_type=bearer');

    await waitFor(() => {
      expect(screen.getByText('home-probe')).toBeInTheDocument();
    });
    const state = useAuthStore.getState();
    expect(state.accessToken).toBe('abc');
    expect(state.refreshToken).toBe('def');
    expect(state.isAuthenticated).toBe(true);
    expect(state.user?.display_name).toBe('SSO User');
    // The fragment must be cleared from the URL.
    expect(window.location.hash).toBe('');
  });

  it('redirects to profile when no tokens are present (link flow)', async () => {
    renderCallback('/auth/callback');

    await waitFor(() => {
      expect(screen.getByText('profile-probe')).toBeInTheDocument();
    });
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it('shows an error for provider denial (?error=access_denied)', async () => {
    window.history.replaceState({}, '', '/auth/callback?error=access_denied');

    renderCallback('/auth/callback');

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('access_denied');
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });
});
