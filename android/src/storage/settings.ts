import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY_SERVER_URL = 'dp_server_url';
const KEY_THEME = 'dp_theme';
const KEY_COOKIE_JAR = 'dp_cookie_jar';

export async function getServerUrl(): Promise<string | null> {
  return AsyncStorage.getItem(KEY_SERVER_URL);
}

export async function setServerUrl(url: string): Promise<void> {
  const trimmed = url.trim().replace(/\/$/, '');
  await AsyncStorage.setItem(KEY_SERVER_URL, trimmed);
}

export type ThemePref = 'system' | 'dark' | 'light';

export async function getThemePref(): Promise<ThemePref> {
  const v = await AsyncStorage.getItem(KEY_THEME);
  if (v === 'dark' || v === 'light' || v === 'system') return v;
  return 'system';
}

export async function setThemePref(pref: ThemePref): Promise<void> {
  await AsyncStorage.setItem(KEY_THEME, pref);
}

export async function getCookieJarJson(): Promise<string | null> {
  return AsyncStorage.getItem(KEY_COOKIE_JAR);
}

export async function setCookieJarJson(json: string): Promise<void> {
  await AsyncStorage.setItem(KEY_COOKIE_JAR, json);
}

export async function clearCookieJar(): Promise<void> {
  await AsyncStorage.removeItem(KEY_COOKIE_JAR);
}

export async function clearAll(): Promise<void> {
  await AsyncStorage.multiRemove([KEY_COOKIE_JAR]);
}
