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

  const { data, isLoading, isError } = useQuery({
    queryKey: ['books', 'autocomplete', trimmedQuery],
    queryFn: () => booksApi.autocomplete(trimmedQuery).then((res) => res.data),
    enabled,
    staleTime: 30_000,
  });

  return useMemo(() => {
    const suggestions: AutocompleteSuggestion[] = data?.suggestions ?? [];
    return {
      suggestions,
      isLoading: enabled && isLoading,
      isError: enabled && isError,
    };
  }, [data, enabled, isLoading, isError]);
}

export default useAutocomplete;
