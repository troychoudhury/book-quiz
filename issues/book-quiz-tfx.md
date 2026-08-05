# Add Single Sign-On (SSO) with Google, Facebook, and Microsoft

**Bead**: book-quiz-tfx | **Status**: Requirements

## Description

OAuth2 SSO with Google, Facebook, Microsoft. Recommended additional: Apple, Clever, GitHub.

## Agent Log

| Date | Agent | Action | Summary |
|------|-------|--------|---------|
| 2026-08-04 | tech-lead | created | SSO feature request filed |

## Requirements Clarification

*Product Manager — 2026-08-05*

### Q1: OAuth Flow — Server-Side Authorization Code Grant with PKCE

**Decision: Server-side (Authorization Code + PKCE).**

Client-side implicit/popup flows are deprecated in OAuth 2.1 (RFC 8252). The backend
must exchange an authorization code (and PKCE code verifier) for provider tokens
server-to-server, then issue the app's own JWT. The frontend never sees provider
tokens.

**Flow:**
1. Frontend redirects browser to `/api/v1/auth/oauth/{provider}/login`
2. Backend generates PKCE `code_verifier` + `code_challenge`, redirects to provider
3. Provider calls back to `/api/v1/auth/oauth/{provider}/callback?code=...&state=...`
4. Backend exchanges code for provider tokens, fetches user info, creates/links account, issues JWT
5. Backend redirects browser to frontend callback URL with JWT in URL fragment or query (one-time code)

**Rationale:**
- Provider tokens stay server-side — no XSS leak risk
- PKCE prevents authorization code interception (required for mobile, best practice everywhere)
- Aligned with existing JWT stateless architecture
- The `state` parameter (with HMAC signing) prevents CSRF on the callback

### Q2: User Data Collected from Providers

**Decision: email (required), display_name, avatar_url.**

| Provider | Userinfo Endpoint | Fields Used |
|----------|-------------------|-------------|
| Google | `https://openidconnect.googleapis.com/v1/userinfo` | `email`, `name`, `picture` |
| Facebook | `GET /me?fields=id,name,email,picture` (Graph API v19+) | `email`, `name`, `picture.data.url` |
| Microsoft | `https://graph.microsoft.com/v1.0/me` | `mail` or `userPrincipalName`, `displayName` |

**Rationale:**
- `email` is the only strictly required field — it's the account identity anchor
- `display_name` maps to the existing `users.display_name` column
- `avatar_url` is a new optional column (`VARCHAR(500)`) on the `users` table
- We do NOT collect: provider-specific IDs (stored in link table only), birthdates, friends lists, or other sensitive scopes
- All three providers return verified emails — we can trust the email verification

**Schema changes needed:**
- `users.password_hash` → nullable (SSO-only accounts have no password)
- `users.avatar_url` → new column, nullable
- New table: `user_oauth_links(user_id, provider, provider_user_id, linked_at)`

### Q3: Account Merging — Auto-Link by Verified Email

**Decision: Auto-link when SSO email matches existing account email.**

If a user signs in with Google and `google-returned-email@gmail.com` matches
`users.email`, the OAuth provider is linked to the existing account automatically
and the user is logged in.

**Rationale:**
- OAuth providers verify emails before returning them — the email is trusted
- Prompting "Looks like you have an account, want to link?" adds friction for zero security gain
- This is the standard behavior for Auth0, Firebase Auth, Supabase Auth, and most SaaS
- Existing email/password users can add SSO trivially by logging in with the provider once

**Edge case — email mismatch:** If the SSO email doesn't match any user, a new
account is created. If the user intended to link but used a different email on
the provider, they'll end up with two accounts. Mitigation: profile page allows
linking additional providers after login.

### Q4: Password Login for SSO-Created Accounts

**Decision: No — SSO-created accounts cannot use password login.**

SSO-only accounts have `password_hash = NULL`. Until a "Set Password" feature
is built (future), these users must always log in via their OAuth provider.

**Implications:**
- `POST /auth/login` (email+password) returns 401 for accounts with `password_hash IS NULL`
- Profile page shows "Password: Not set" with a disabled "Set Password" button (future)
- The `RegisterRequest` model remains unchanged (email+password signup is separate)

### Q5: Frontend — SSO Buttons Above Email/Password Form

**Decision: Separate SSO buttons with a visual divider, NOT tabs.**

```
┌──────────────────────────────┐
│  [G] Sign in with Google     │
│  [f] Sign in with Facebook   │
│  [M] Sign in with Microsoft  │
│                              │
│  ─────── or continue ─────── │
│  Email:    [            ]    │
│  Password: [            ]    │
│  [Sign In]  [Create Account] │
└──────────────────────────────┘
```

**Rationale:**
- SSO is the preferred path for most users (faster, no password fatigue)
- Tabs hide options; visible buttons encourage SSO adoption
- This is the dominant UX pattern (Google, GitHub, Notion, Linear all use it)
- On mobile, buttons stack vertically with the same layout
- The login and signup pages share the same SSO buttons (both lead to the same
  OAuth flow — if the email matches an account, it logs in; if not, it creates one)

### Q6: User Revokes Access on Provider Side

**Decision: Handle at next login — no proactive detection needed.**

When a user revokes Book Quiz's access in their Google/Facebook/Microsoft account
settings, the provider invalidates the refresh token (which we don't store — we only
exchange the code once). The impact surfaces at the next SSO login attempt:

1. User clicks "Sign in with Google"
2. Google shows the consent screen again (because access was revoked)
3. If user re-consents, we get a new token — normal flow continues
4. If user denies, the login fails with a user-friendly error

**We do NOT:**
- Store or reuse provider refresh tokens (only need identity at login time)
- Proactively poll providers for revocation status
- Invalidate existing app JWTs if provider access is revoked (JWT is stateless — it's valid until expiry)

### Q7: Account Unlinking

**Decision: Allow unlinking only when ≥1 alternative auth method remains.**

From the profile page, users can unlink specific providers. Constraints:
- Cannot unlink the last remaining provider if `password_hash IS NULL`
- Cannot unlink all providers if `password_hash IS NULL` (must have password OR another provider)
- Cannot "delete" the password (future feature)
- Unlinking removes the `user_oauth_links` row; the user account persists

**API:**
- `GET /api/v1/users/me/oauth-links` — list linked providers
- `DELETE /api/v1/users/me/oauth-links/{provider}` — unlink (enforces above constraints)

### Q8: Environment Variables Required Per Provider

**Decision: Eight new env vars, plus one shared.**

| Variable | Description |
|----------|-------------|
| `OAUTH_GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `OAUTH_GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `OAUTH_FACEBOOK_CLIENT_ID` | Facebook App ID |
| `OAUTH_FACEBOOK_CLIENT_SECRET` | Facebook App secret |
| `OAUTH_MICROSOFT_CLIENT_ID` | Microsoft Entra ID Application (client) ID |
| `OAUTH_MICROSOFT_CLIENT_SECRET` | Microsoft client secret (value, not ID) |
| `OAUTH_REDIRECT_BASE_URL` | Base URL for OAuth callbacks (default: `http://localhost:8000`) |
| `OAUTH_FRONTEND_CALLBACK_URL` | Frontend URL to redirect after successful OAuth (default: `http://localhost:5173/auth/callback`) |

Each provider is optional — if CLIENT_ID is empty, that provider's button is hidden
and its endpoints return 404. This allows gradual rollout and makes self-hosting simple.

**Callback URLs to register with each provider:**
- Google: `{OAUTH_REDIRECT_BASE_URL}/api/v1/auth/oauth/google/callback`
- Facebook: `{OAUTH_REDIRECT_BASE_URL}/api/v1/auth/oauth/facebook/callback`
- Microsoft: `{OAUTH_REDIRECT_BASE_URL}/api/v1/auth/oauth/microsoft/callback`

---

### Summary: API Endpoints Needed

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/auth/oauth/{provider}/login` | None | Initiate OAuth flow; redirects to provider |
| `GET` | `/api/v1/auth/oauth/{provider}/callback` | None | OAuth callback; exchanges code, issues JWT, redirects to frontend |
| `GET` | `/api/v1/users/me/oauth-links` | JWT | List linked OAuth providers for current user |
| `DELETE` | `/api/v1/users/me/oauth-links/{provider}` | JWT | Unlink a provider (with constraints) |

### Summary: Schema Changes

1. `users.password_hash` → `nullable=True`
2. `users.avatar_url` → new column `VARCHAR(500)`, nullable
3. New table: `user_oauth_links`
   - `id UUID PK`
   - `user_id UUID FK → users.id ON DELETE CASCADE`
   - `provider VARCHAR(20) NOT NULL` (one of: `google`, `facebook`, `microsoft`)
   - `provider_user_id VARCHAR(255) NOT NULL`
   - `linked_at TIMESTAMPTZ NOT NULL DEFAULT now()`
   - `UNIQUE(provider, provider_user_id)` — one provider ID can only be linked to one account
   - `UNIQUE(user_id, provider)` — one user can only link each provider once

### User Story Summary

1. **As a new user**, I want to sign up with my Google account, so I can start taking quizzes without creating a new password.
2. **As an existing user**, I want to link my Google account to my email/password account, so I can log in faster.
3. **As a returning user**, I want to log in with any linked provider, so I don't have to remember which method I used.
4. **As a security-conscious user**, I want to unlink a provider I no longer use, so my account is only accessible via my preferred methods.
5. **As a student**, I want to log in with my school Microsoft account, so I can use the same login I use for school.

### Acceptance Criteria (Gherkin)

```gherkin
Feature: SSO Login
  Scenario: Sign up with Google for the first time
    Given I am not logged in
    When I click "Sign in with Google"
    And I authorize Book Quiz on the Google consent screen
    Then I am redirected back to the app
    And I am logged in with a valid access token
    And my display name and avatar are set from my Google profile

  Scenario: Log in with Google after signing up
    Given I have an account linked to Google
    And I am logged out
    When I click "Sign in with Google"
    Then I am logged in immediately (no consent screen if previously authorized)

  Scenario: Auto-link when SSO email matches existing account
    Given I have an email/password account with email "alice@example.com"
    And I am logged out
    When I click "Sign in with Google" with the same email "alice@example.com"
    Then my Google account is linked to my existing account
    And I am logged in

  Scenario: Prevent unlinking last auth method
    Given I have only a Google-linked account (no password)
    When I try to unlink Google from my profile
    Then the request is rejected with a message to set a password first

  Scenario: Unlink when multiple auth methods exist
    Given I have both Google and Facebook linked
    When I unlink Facebook from my profile
    Then Facebook is removed from my linked providers
    And I can still log in with Google
```

### RICE Prioritization

| Component | Reach | Impact | Confidence | Effort | RICE Score |
|-----------|-------|--------|------------|--------|------------|
| Google SSO | High (everyone has Google) | High (fastest signup flow) | 90% | 3 days | 30.0 |
| Microsoft SSO | Medium (K-12 education focus) | High (critical for schools) | 85% | 2.5 days | 20.4 |
| Facebook SSO | Medium (social familiarity) | Medium (less for edu) | 85% | 2 days | 18.0 |
| Provider linking/unlinking (API) | Medium | Medium | 85% | 1.5 days | 14.2 |
| Avatar support | Medium | Low (nice-to-have) | 90% | 0.5 days | 13.5 |
| Frontend SSO buttons + callback page | High | Medium | 85% | 2 days | 25.5 |

**Recommended implementation order (Phase 1):** Google SSO → Microsoft SSO → Facebook SSO → Frontend UI → Linking API. All three providers can share the same OAuth infrastructure (abstract base, per-provider config).

## Architecture Plan

*Pending architect delegation.*

## Plan Review

*Pending.*

## Implementation Notes

*Pending.*

## Code Review

*Pending.*

## Security Audit

*Pending.*

## Test Results

*Pending.*
