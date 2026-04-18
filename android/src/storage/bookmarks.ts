import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = 'dp_bookmarks';

export async function getBookmarks(): Promise<Set<string>> {
  const raw = await AsyncStorage.getItem(KEY);
  if (!raw) return new Set();
  try {
    return new Set(JSON.parse(raw));
  } catch {
    return new Set();
  }
}

export async function toggleBookmark(arxivId: string): Promise<boolean> {
  const bm = await getBookmarks();
  if (bm.has(arxivId)) {
    bm.delete(arxivId);
  } else {
    bm.add(arxivId);
  }
  await AsyncStorage.setItem(KEY, JSON.stringify([...bm]));
  return bm.has(arxivId);
}

export async function isBookmarked(arxivId: string): Promise<boolean> {
  const bm = await getBookmarks();
  return bm.has(arxivId);
}
