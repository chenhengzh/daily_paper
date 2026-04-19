import { useState, useCallback } from 'react';
import { bookmarkPaper, unbookmarkPaper } from '../api/papers';

export function useBookmarks(initialBookmarks: Set<string> = new Set()) {
  const [bookmarks, setBookmarks] = useState<Set<string>>(initialBookmarks);

  const toggle = useCallback(async (arxivId: string) => {
    const isCurrentlyBookmarked = bookmarks.has(arxivId);
    // Optimistic update
    setBookmarks(prev => {
      const next = new Set(prev);
      if (isCurrentlyBookmarked) {
        next.delete(arxivId);
      } else {
        next.add(arxivId);
      }
      return next;
    });
    try {
      if (isCurrentlyBookmarked) {
        await unbookmarkPaper(arxivId);
      } else {
        await bookmarkPaper(arxivId);
      }
    } catch {
      // Revert on failure
      setBookmarks(prev => {
        const next = new Set(prev);
        if (isCurrentlyBookmarked) {
          next.add(arxivId);
        } else {
          next.delete(arxivId);
        }
        return next;
      });
    }
  }, [bookmarks]);

  return { bookmarks, toggle, setBookmarks };
}
