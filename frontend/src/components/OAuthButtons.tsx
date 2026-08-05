import { useEffect, useState } from 'react';

import { API_BASE, oauthApi } from '../services/api';
import type { OAuthProvider } from '../types';

const PROVIDER_STYLES: Record<string, { label: string; icon: string; className: string }> = {
  google: {
    label: 'Google',
    icon: 'G',
    className: 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50',
  },
  facebook: {
    label: 'Facebook',
    icon: 'f',
    className: 'bg-[#1877F2] text-white hover:bg-[#166FE5]',
  },
  microsoft: {
    label: 'Microsoft',
    icon: 'M',
    className: 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50',
  },
};

/**
 * SSO provider buttons for the login/signup pages.
 *
 * Each button is a plain link to the backend OAuth initiation endpoint — the
 * browser must follow the full redirect chain (app → provider → app), so the
 * first hop cannot be a fetch call (see issues/book-quiz-tfx.md §1.4).
 */
export default function OAuthButtons() {
  const [providers, setProviders] = useState<OAuthProvider[]>([]);

  useEffect(() => {
    oauthApi
      .getOAuthProviders()
      .then(({ data }) => setProviders(data.providers))
      .catch(() => setProviders([]));
  }, []);

  if (providers.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      {providers.map((provider) => {
        const style = PROVIDER_STYLES[provider.provider] ?? {
          label: provider.name,
          icon: provider.name.charAt(0),
          className: 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50',
        };
        return (
          <a
            key={provider.provider}
            href={`${API_BASE}/api/v1/auth/oauth/${provider.provider}/login`}
            className={`flex w-full items-center justify-center gap-3 rounded-lg py-2 text-sm font-medium transition ${style.className}`}
          >
            <span aria-hidden="true" className="font-bold">
              {style.icon}
            </span>
            Sign in with {style.label}
          </a>
        );
      })}
      <div
        className="flex items-center gap-3 py-2"
        role="separator"
        aria-label="or continue with email"
      >
        <div className="flex-1 border-t border-gray-200" />
        <span className="text-xs text-gray-500">or continue with email</span>
        <div className="flex-1 border-t border-gray-200" />
      </div>
    </div>
  );
}
