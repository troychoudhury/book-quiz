import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';

import { booksApi } from '../services/api';
import type { BookSummary } from '../types';

export default function SearchResultsPage() {
  const [searchParams] = useSearchParams();
  const query = searchParams.get('q') ?? '';

  const { data, isLoading, isError } = useQuery({
    queryKey: ['books', query],
    queryFn: () => booksApi.search(query).then((res) => res.data),
    enabled: query.length > 0,
  });

  const results: BookSummary[] = data?.items ?? [];

  return (
    <main className="max-w-4xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold mb-2">
        {query ? (
          <>
            Results for &quot;{query}&quot;
            <span className="text-gray-500 text-lg ml-2">({data?.total ?? 0})</span>
          </>
        ) : (
          'Search books'
        )}
      </h1>

      {isLoading && <p className="text-gray-500 py-8 text-center">Searching...</p>}

      {isError && (
        <div className="p-4 bg-red-50 text-red-700 rounded-lg my-4">
          Failed to search books. Please try again.
        </div>
      )}

      {!isLoading && !isError && query && results.length === 0 && (
        <p className="text-gray-500 py-8 text-center">
          No books found for &quot;{query}&quot;. Try a different title or ISBN.
        </p>
      )}

      {!isLoading && !isError && query.length === 0 && (
        <p className="text-gray-500 py-8 text-center">Type a book title or ISBN to search.</p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
        {results.map((book) => (
          <Link
            key={book.id}
            to={`/books/${book.id}`}
            className="bg-white rounded-xl shadow-sm p-4 hover:shadow-md transition flex gap-4"
          >
            <div className="w-16 h-24 bg-gray-100 rounded flex-shrink-0 overflow-hidden">
              {book.cover_url ? (
                <img src={book.cover_url} alt="" className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-2xl">📖</div>
              )}
            </div>
            <div className="min-w-0">
              <h3 className="font-semibold text-gray-900 truncate">{book.title}</h3>
              <p className="text-sm text-gray-600">{book.author}</p>
              {book.isbn && <p className="text-xs text-gray-400 mt-1">ISBN: {book.isbn}</p>}
              <p className="text-xs text-blue-600 mt-2">
                {book.question_count > 0 ? `${book.question_count} questions` : 'Take the quiz'}
              </p>
            </div>
          </Link>
        ))}
      </div>
    </main>
  );
}
