import { useState, useEffect, useCallback } from 'react';
import { getBookmarks, toggleBookmark } from '../storage/bookmarks';

export function useBookmarks() {
  const [bookmarks, setBookmarks] = useState<Set<string>>(new Set());

  useEffect(() => {
    getBookmarks().then(setBookmarks);
  }, []);

  const toggle = useCallback(async (arxivId: string) => {
    await toggleBookmark(arxivId);
    const updated = await getBookmarks();
    setBookmarks(new Set(updated));
  }, []);

  return { bookmarks, toggle };
}
