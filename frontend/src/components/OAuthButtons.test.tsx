import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { oauthApi } from '../services/api';
import OAuthButtons from './OAuthButtons';

vi.mock('../services/api', () => ({
  API_BASE: 'http://localhost:8000',
  oauthApi: {
    getOAuthProviders: vi.fn(),
  },
}));

describe('OAuthButtons', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a button per configured provider as a direct link', async () => {
    vi.mocked(oauthApi.getOAuthProviders).mockResolvedValue({
      data: {
        providers: [
          { provider: 'google', name: 'Google' },
          { provider: 'microsoft', name: 'Microsoft' },
        ],
      },
    } as never);

    render(<OAuthButtons />);

    const googleLink = await screen.findByRole('link', { name: /sign in with google/i });
    expect(googleLink).toHaveAttribute(
      'href',
      'http://localhost:8000/api/v1/auth/oauth/google/login',
    );
    expect(screen.getByRole('link', { name: /sign in with microsoft/i })).toBeInTheDocument();
    expect(screen.getByRole('separator', { name: /or continue with email/i })).toBeInTheDocument();
  });

  it('renders nothing when the API returns no providers', async () => {
    vi.mocked(oauthApi.getOAuthProviders).mockResolvedValue({
      data: { providers: [] },
    } as never);

    const { container } = render(<OAuthButtons />);
    await waitFor(() => {
      expect(oauthApi.getOAuthProviders).toHaveBeenCalledTimes(1);
    });
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when the providers request fails', async () => {
    vi.mocked(oauthApi.getOAuthProviders).mockRejectedValue(new Error('network down'));

    const { container } = render(<OAuthButtons />);
    await waitFor(() => {
      expect(oauthApi.getOAuthProviders).toHaveBeenCalledTimes(1);
    });
    expect(container.firstChild).toBeNull();
  });
});
