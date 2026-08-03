import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import Layout from '../components/Layout';

function renderLayout() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Layout />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Layout', () => {
  it('renders the book quiz logo', () => {
    renderLayout();
    expect(screen.getByRole('link', { name: /book quiz/i })).toBeInTheDocument();
  });

  it('renders login and sign up links for guests', () => {
    renderLayout();
    expect(screen.getByRole('link', { name: /log in/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /sign up/i })).toBeInTheDocument();
  });

  it('renders a search input', () => {
    renderLayout();
    expect(screen.getByLabelText('Search books')).toBeInTheDocument();
  });
});
