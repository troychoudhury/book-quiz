import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useAutocomplete } from '../hooks/useAutocomplete';
import type { AutocompleteSuggestion } from '../types';

export interface SearchBarProps {
  /** 'hero' (landing page) is large with a visible submit button; 'header' is compact. */
  variant?: 'hero' | 'header';
  autoFocus?: boolean;
}

const MIN_QUERY_LENGTH = 2;
const ERROR_HINT_MS = 800;

/**
 * Shared search combobox with typeahead suggestions.
 *
 * ARIA combobox pattern (role="combobox", aria-expanded, aria-autocomplete,
 * aria-activedescendant) plus full keyboard support: ArrowDown/ArrowUp wrap,
 * Enter navigates to the highlighted book (or the search page), Escape closes.
 */
export default function SearchBar({ variant = 'hero', autoFocus = false }: SearchBarProps) {
  const [query, setQuery] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [showErrorHint, setShowErrorHint] = useState(false);
  const [openUpward, setOpenUpward] = useState(false);

  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const errorTimerRef = useRef<number | null>(null);

  // M2: instance-scoped ARIA ids so two mounted SearchBars never collide.
  const listboxId = useId();
  const optionId = (index: number) => `${listboxId}-option-${index}`;

  const { suggestions, isLoading, isFetched, isError, isPending } = useAutocomplete(query);

  const isHero = variant === 'hero';
  const trimmedQuery = query.trim();
  const dropdownVisible = isOpen && trimmedQuery.length >= MIN_QUERY_LENGTH;

  // R5: track the visual viewport so the dropdown clears the on-screen
  // keyboard on mobile instead of being hidden behind it.
  const updatePosition = useCallback(() => {
    if (!inputRef.current || typeof window === 'undefined' || !window.visualViewport) return;
    const rect = inputRef.current.getBoundingClientRect();
    const visualHeight = window.visualViewport.height;
    setOpenUpward(rect.bottom > visualHeight / 2);
  }, []);

  useEffect(() => {
    const visualViewport = window.visualViewport;
    if (!visualViewport) return;
    updatePosition();
    visualViewport.addEventListener('resize', updatePosition);
    visualViewport.addEventListener('scroll', updatePosition);
    return () => {
      visualViewport.removeEventListener('resize', updatePosition);
      visualViewport.removeEventListener('scroll', updatePosition);
    };
  }, [updatePosition, dropdownVisible]);

  // API errors fail silently: close the dropdown and flash an amber input
  // border so typing is never interrupted (spec: "silently fails").
  useEffect(() => {
    if (!isError) return;
    setIsOpen(false);
    setHighlightedIndex(-1);
    setShowErrorHint(true);
    if (errorTimerRef.current !== null) window.clearTimeout(errorTimerRef.current);
    errorTimerRef.current = window.setTimeout(() => setShowErrorHint(false), ERROR_HINT_MS);
  }, [isError]);

  useEffect(
    () => () => {
      if (errorTimerRef.current !== null) window.clearTimeout(errorTimerRef.current);
    },
    [],
  );

  const submitSearch = useCallback(() => {
    const trimmed = query.trim();
    if (!trimmed) return;
    setIsOpen(false);
    setHighlightedIndex(-1);
    navigate(`/search?q=${encodeURIComponent(trimmed)}`);
  }, [query, navigate]);

  const handleSelect = useCallback(
    (suggestion: AutocompleteSuggestion) => {
      setIsOpen(false);
      setHighlightedIndex(-1);
      navigate(`/books/${suggestion.id}`);
    },
    [navigate],
  );

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setQuery(e.target.value);
    setHighlightedIndex(-1);
    setIsOpen(true);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!dropdownVisible) {
      if (e.key === 'Enter') {
        e.preventDefault();
        submitSearch();
      }
      return;
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        if (suggestions.length > 0) {
          setHighlightedIndex((i) => (i + 1) % suggestions.length);
        }
        break;
      case 'ArrowUp':
        e.preventDefault();
        if (suggestions.length > 0) {
          setHighlightedIndex((i) => (i <= 0 ? suggestions.length - 1 : i - 1));
        }
        break;
      case 'Enter':
        e.preventDefault();
        if (highlightedIndex >= 0 && suggestions[highlightedIndex]) {
          handleSelect(suggestions[highlightedIndex]);
        } else {
          submitSearch();
        }
        break;
      case 'Escape':
        e.preventDefault();
        setIsOpen(false);
        setHighlightedIndex(-1);
        inputRef.current?.blur();
        break;
      case 'Tab':
        setIsOpen(false);
        setHighlightedIndex(-1);
        break;
      default:
        break;
    }
  };

  // R3: suggestion selection uses onMouseDown (fires before blur), so a
  // genuine outside click can close the dropdown immediately — no delay hack.
  const handleBlur = () => {
    setIsOpen(false);
    setHighlightedIndex(-1);
  };

  const inputClasses = [
    'w-full rounded-full focus:outline-none focus:border-blue-500 transition-colors',
    isHero ? 'px-6 py-4 text-lg border-2 shadow-sm pr-28' : 'px-4 py-2 text-sm border',
    showErrorHint ? 'border-amber-400' : 'border-gray-300',
  ].join(' ');

  return (
    <div className={`relative ${isHero ? 'w-full max-w-xl mx-auto' : 'w-full'}`}>
      <input
        ref={inputRef}
        type="text"
        value={query}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onBlur={handleBlur}
        autoFocus={autoFocus}
        autoComplete="off"
        maxLength={200}
        placeholder={isHero ? 'Search by book title or author...' : 'Search books...'}
        aria-label={isHero ? 'Search for a book' : 'Search books'}
        role="combobox"
        aria-expanded={dropdownVisible}
        aria-autocomplete="list"
        aria-controls={listboxId}
        aria-activedescendant={
          dropdownVisible && highlightedIndex >= 0 ? optionId(highlightedIndex) : undefined
        }
        className={inputClasses}
      />

      {isHero && (
        <button
          type="button"
          onClick={submitSearch}
          className="absolute right-2 top-1/2 -translate-y-1/2 bg-blue-600 text-white px-6 py-2 rounded-full hover:bg-blue-700 transition"
        >
          Search
        </button>
      )}

      {dropdownVisible && (
        <div
          className={`absolute z-20 w-full overflow-hidden rounded-xl bg-white shadow-lg ring-1 ring-gray-200 ${
            openUpward ? 'bottom-full mb-2' : 'top-full mt-2'
          }`}
        >
          {suggestions.length > 0 ? (
            <ul id={listboxId} role="listbox" aria-label="Search suggestions" aria-live="polite" className="max-h-64 overflow-y-auto">
              {suggestions.map((suggestion, index) => (
                <li
                  key={suggestion.id}
                  id={optionId(index)}
                  role="option"
                  aria-selected={index === highlightedIndex}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    handleSelect(suggestion);
                  }}
                  onMouseEnter={() => setHighlightedIndex(index)}
                  className={`flex cursor-pointer items-center gap-3 px-3 py-2 ${
                    index === highlightedIndex ? 'bg-blue-50' : ''
                  }`}
                >
                  <span className="flex h-10 w-8 flex-shrink-0 items-center justify-center overflow-hidden rounded bg-gray-100 text-sm">
                    {suggestion.cover_url?.startsWith('https://') ? (
                      <img
                        src={suggestion.cover_url}
                        alt=""
                        referrerPolicy="no-referrer"
                        loading="lazy"
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      '📖'
                    )}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium text-gray-900">
                      {suggestion.title}
                    </span>
                    <span className="block truncate text-xs text-gray-500">
                      {suggestion.author}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          ) : isLoading || isPending ? (
            <div
              role="status"
              className="flex items-center justify-center gap-2 px-4 py-3 text-sm text-gray-500"
            >
              <span
                className="h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600"
                aria-hidden="true"
              />
              Searching...
            </div>
          ) : isFetched && !isLoading && !isError ? (
            <div className="px-4 py-3 text-sm text-gray-500">No matching books found</div>
          ) : null}
          {/* Loading indicator below existing results during re-fetch */}
          {suggestions.length > 0 && isLoading && (
            <div className="flex items-center justify-center gap-2 border-t border-gray-100 px-4 py-2 text-xs text-gray-400">
              <span
                className="h-3 w-3 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600"
                aria-hidden="true"
              />
              Updating...
            </div>
          )}
        </div>
      )}
    </div>
  );
}
