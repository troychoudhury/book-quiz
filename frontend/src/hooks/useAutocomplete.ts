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
    // N2: while the typed query hasn't settled into the debounced value yet,
    // blank suggestions so stale results from the previous debounce window are
    // never shown. isFetched is also suppressed during this window so consumers
    // never flash a false "No matching books found" message (M1).
    const isStale = query !== debouncedQuery;
    const suggestions: AutocompleteSuggestion[] = isStale ? [] : (data?.suggestions ?? []);

    return {
      suggestions,
      isLoading: isStale || (enabled && isLoading),
      isFetched: enabled && !isStale && isFetched,
      isError: enabled && !isStale && isError,
    };
  }, [query, debouncedQuery, data, enabled, isLoading, isFetched, isError]);
}

export default useAutocomplete;
