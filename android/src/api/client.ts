import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';

const COOKIE_KEY = 'dp_cookies';

// In-memory cookie store: { [name]: value }
let cookieStore: Record<string, string> = {};

export const client = axios.create({
  timeout: 30000,
  maxRedirects: 0,
});

let _baseURL = '';

export function setBaseURL(url: string) {
  _baseURL = url;
  client.defaults.baseURL = url;
}

export function getBaseURL(): string {
  return _baseURL;
}

// Attach cookies to every request
client.interceptors.request.use((config) => {
  const cookieHeader = Object.entries(cookieStore)
    .map(([k, v]) => `${k}=${v}`)
    .join('; ');
  if (cookieHeader) {
    config.headers = config.headers ?? {};
    config.headers['Cookie'] = cookieHeader;
  }
  return config;
});

// Parse and persist Set-Cookie from every response
client.interceptors.response.use(
  async (response) => {
    await _extractCookies(response);
    return response;
  },
  async (error) => {
    if (error.response) {
      await _extractCookies(error.response);
    }
    return Promise.reject(error);
  }
);

async function _extractCookies(response: any) {
  try {
    const setCookie: string | string[] | undefined =
      response.headers['set-cookie'];
    if (!setCookie) return;
    const cookies = Array.isArray(setCookie) ? setCookie : [setCookie];
    for (const raw of cookies) {
      const part = raw.split(';')[0].trim();
      const eq = part.indexOf('=');
      if (eq < 0) continue;
      const name = part.slice(0, eq).trim();
      const value = part.slice(eq + 1).trim();
      if (name) cookieStore[name] = value;
    }
    await AsyncStorage.setItem(COOKIE_KEY, JSON.stringify(cookieStore));
  } catch {}
}

export async function restoreCookieJar(): Promise<void> {
  try {
    const saved = await AsyncStorage.getItem(COOKIE_KEY);
    if (saved) cookieStore = JSON.parse(saved);
  } catch {}
}

export async function clearSession(): Promise<void> {
  cookieStore = {};
  await AsyncStorage.removeItem(COOKIE_KEY);
}
