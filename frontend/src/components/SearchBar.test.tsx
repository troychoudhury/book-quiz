import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi, type Mock } from 'vitest';

import SearchBar from './SearchBar';
import { booksApi } from '../services/api';
import type { AutocompleteResponse } from '../types';

vi.mock('../services/api', () => ({
  booksApi: {
    autocomplete: vi.fn(),
    search: vi.fn(),
    getById: vi.fn(),
  },
}));

const suggestions: AutocompleteResponse = {
  suggestions: [
    {
      id: 'book-1',
      title: "Harry Potter and the Sorcerer's Stone",
      author: 'J.K. Rowling',
      cover_url: null,
    },
    {
      id: 'book-2',
      title: 'Harry Potter and the Chamber of Secrets',
      author: 'J.K. Rowling',
      cover_url: 'https://example.com/cover.jpg',
    },
  ],
};

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location">{location.pathname + location.search}</span>;
}

function renderSearchBar(variant: 'hero' | 'header' = 'hero', withRoutes = false) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  const searchBar = <SearchBar variant={variant} />;

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        {withRoutes ? (
          <Routes>
            <Route
              path="/"
              element={
                <>
                  {searchBar}
                  <LocationProbe />
                </>
              }
            />
            <Route path="/books/:bookId" element={<LocationProbe />} />
            <Route path="/search" element={<LocationProbe />} />
          </Routes>
        ) : (
          searchBar
        )}
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('SearchBar', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('shows suggestions after the debounce delay', async () => {
    (booksApi.autocomplete as Mock).mockResolvedValue({ data: suggestions });
    renderSearchBar();

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'harry' } });
    expect(booksApi.autocomplete).not.toHaveBeenCalled();

    await waitFor(() => {
      expect(booksApi.autocomplete).toHaveBeenCalledWith('harry');
    });

    const options = await screen.findAllByRole('option');
    expect(options).toHaveLength(2);
    expect(options[0]).toHaveTextContent("Harry Potter and the Sorcerer's Stone");
    expect(options[0]).toHaveTextContent('J.K. Rowling');
  });

  it('does not call the API for queries under 2 characters', async () => {
    renderSearchBar();
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'h' } });
    await new Promise((resolve) => setTimeout(resolve, 350));
    expect(booksApi.autocomplete).not.toHaveBeenCalled();
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('closes the dropdown on Escape and keeps the typed text', async () => {
    (booksApi.autocomplete as Mock).mockResolvedValue({ data: suggestions });
    renderSearchBar();

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'harry' } });
    expect(await screen.findByRole('listbox')).toBeInTheDocument();

    fireEvent.keyDown(input, { key: 'Escape' });
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(input).toHaveValue('harry');
  });

  it('navigates to the highlighted book on ArrowDown + Enter', async () => {
    (booksApi.autocomplete as Mock).mockResolvedValue({ data: suggestions });
    renderSearchBar('hero', true);

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'harry' } });
    await waitFor(() => {
      expect(booksApi.autocomplete).toHaveBeenCalledWith('harry');
    });
    expect(await screen.findAllByRole('option')).toHaveLength(2);

    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(input).toHaveAttribute('aria-activedescendant', 'suggestion-0');
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(input).toHaveAttribute('aria-activedescendant', 'suggestion-1');
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('/books/book-2');
    });
  });

  it('navigates to the search page on Enter without a selection', async () => {
    (booksApi.autocomplete as Mock).mockResolvedValue({ data: suggestions });
    renderSearchBar('hero', true);

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'harry' } });
    await waitFor(() => {
      expect(booksApi.autocomplete).toHaveBeenCalledWith('harry');
    });
    expect(await screen.findAllByRole('option')).toHaveLength(2);

    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('/search?q=harry');
    });
  });

  it('shows an empty state when no books match', async () => {
    (booksApi.autocomplete as Mock).mockResolvedValue({ data: { suggestions: [] } });
    renderSearchBar();

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'zzz' } });
    expect(await screen.findByText('No matching books found')).toBeInTheDocument();
  });

  it('silently closes the dropdown when the API fails', async () => {
    (booksApi.autocomplete as Mock).mockRejectedValue(new Error('network down'));
    renderSearchBar();

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'harry' } });

    await waitFor(() => {
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    });
    expect(input).toHaveValue('harry');
  });

  it('renders a submit button only for the hero variant', () => {
    renderSearchBar('hero');
    expect(screen.getByRole('button', { name: /search/i })).toBeInTheDocument();

    cleanup();
    renderSearchBar('header');
    expect(screen.queryByRole('button', { name: /search/i })).not.toBeInTheDocument();
  });
});
