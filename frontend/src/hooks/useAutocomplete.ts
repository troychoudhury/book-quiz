import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { booksApi } from '../services/api';
import type { AutocompleteSuggestion } from '../types';
import { useDebounce } from './useDebounce';

const DEBOUNCE_MS = 300;
const MIN_QUERY_LENGTH = 2;

/**
 * Debounced autocomplete query backed by React Query.
 *
 * No request is fired until the trimmed query is at least 2 characters long.
 * Returns a memoized bundle so consumers don't re-render on identity changes.
 */
export function useAutocomplete(query: string) {
  const debouncedQuery = useDebounce(query, DEBOUNCE_MS);
  const trimmedQuery = debouncedQuery.trim();
  const enabled = trimmedQuery.length >= MIN_QUERY_LENGTH;

  const { data, isLoading, isFetched, isError } = useQuery({
    queryKey: ['books', 'autocomplete', trimmedQuery],
    queryFn: () => booksApi.autocomplete(trimmedQuery).then((res) => res.data),
    enabled,
    staleTime: 30_000,
  });

  return useMemo(() => {
    // Keep previous results visible during debounce/refetch to avoid
    // jarring blink-on-keystroke. Loading state shows a spinner alongside
    // existing suggestions, not instead of them.
    const suggestions: AutocompleteSuggestion[] = data?.suggestions ?? [];

    // True when user has typed >= 2 chars but the debounced query hasn't
    // caught up yet — used to show an initial spinner before first fetch.
    const isPending = query.trim().length >= MIN_QUERY_LENGTH && query !== debouncedQuery;

    return {
      suggestions,
      isLoading: enabled && isLoading,
      isFetched: enabled && isFetched,
      isError: enabled && isError,
      isPending,
    };
  }, [query, debouncedQuery, data, enabled, isLoading, isFetched, isError]);
}

export default useAutocomplete;
