import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
    // N4: restore real timers so tests that rely on real timing stay isolated.
    vi.useRealTimers();
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
    // N4: fake timers + act() instead of a bare setTimeout (fixes act warning).
    // N5: min_length/max_length are enforced server-side (FastAPI 422); this
    // test covers the client-side min-length edge.
    vi.useFakeTimers();
    renderSearchBar();
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'h' } });
    act(() => {
      vi.advanceTimersByTime(350);
    });
    expect(booksApi.autocomplete).not.toHaveBeenCalled();
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('closes the dropdown on Escape, blurs the input, and keeps the typed text', async () => {
    (booksApi.autocomplete as Mock).mockResolvedValue({ data: suggestions });
    renderSearchBar();

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'harry' } });
    expect(await screen.findByRole('listbox')).toBeInTheDocument();

    input.focus();
    expect(input).toHaveFocus();

    fireEvent.keyDown(input, { key: 'Escape' });
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(input).toHaveValue('harry');
    expect(input).not.toHaveFocus();
  });

  it('navigates to the highlighted book on ArrowDown + Enter', async () => {
    (booksApi.autocomplete as Mock).mockResolvedValue({ data: suggestions });
    renderSearchBar('hero', true);

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'harry' } });
    await waitFor(() => {
      expect(booksApi.autocomplete).toHaveBeenCalledWith('harry');
    });
    const options = await screen.findAllByRole('option');
    expect(options).toHaveLength(2);

    // aria-activedescendant must match the (useId-scoped) option id — assert
    // against the rendered option elements rather than hardcoding ids.
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(input.getAttribute('aria-activedescendant')).toBe(options[0].id);
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(input.getAttribute('aria-activedescendant')).toBe(options[1].id);
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('/books/book-2');
    });
  });

  it('wraps the highlight from the first option back to the last on ArrowUp', async () => {
    (booksApi.autocomplete as Mock).mockResolvedValue({ data: suggestions });
    renderSearchBar();

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'harry' } });
    const options = await screen.findAllByRole('option');

    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(input.getAttribute('aria-activedescendant')).toBe(options[0].id);

    fireEvent.keyDown(input, { key: 'ArrowUp' });
    expect(input.getAttribute('aria-activedescendant')).toBe(options[options.length - 1].id);
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

  it('only shows the empty state after the request has resolved', async () => {
    // M1: no false "No matching books found" flash while the debounce window
    // is still open or the request is in flight.
    vi.useFakeTimers();
    (booksApi.autocomplete as Mock).mockResolvedValue({ data: { suggestions: [] } });
    renderSearchBar();

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'zzz' } });

    // Debounce still pending — spinner, never the empty state.
    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(screen.queryByText('No matching books found')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toBeInTheDocument();

    // Debounce fires; once the request resolves, the empty state appears.
    act(() => {
      vi.advanceTimersByTime(300);
    });
    vi.useRealTimers();
    expect(await screen.findByText('No matching books found')).toBeInTheDocument();
  });

  it('shows a loading spinner while the request is in flight', async () => {
    // M4: a never-resolving request keeps the spinner visible (and never shows
    // the empty state).
    vi.useFakeTimers();
    (booksApi.autocomplete as Mock).mockReturnValue(new Promise(() => {}));
    renderSearchBar();

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'harry' } });

    // While the debounce is pending the list is blanked and shows the spinner.
    expect(screen.getByRole('status')).toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(300);
    });

    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByText('No matching books found')).not.toBeInTheDocument();
  });

  it('fires a single API call when typing rapidly (debounce burst)', async () => {
    // M4: rapid keystrokes within the debounce window collapse to one request
    // carrying the final value.
    vi.useFakeTimers();
    (booksApi.autocomplete as Mock).mockResolvedValue({ data: suggestions });
    renderSearchBar();

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'h' } });
    fireEvent.change(input, { target: { value: 'ha' } });
    fireEvent.change(input, { target: { value: 'har' } });
    fireEvent.change(input, { target: { value: 'harr' } });
    fireEvent.change(input, { target: { value: 'harry' } });

    expect(booksApi.autocomplete).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(300);
    });

    expect(booksApi.autocomplete).toHaveBeenCalledTimes(1);
    expect(booksApi.autocomplete).toHaveBeenCalledWith('harry');
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
