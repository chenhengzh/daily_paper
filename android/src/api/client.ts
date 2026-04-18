import axios from 'axios';
import { wrapper } from 'axios-cookiejar-support';
import { CookieJar } from 'tough-cookie';
import { getCookieJarJson, setCookieJarJson, clearCookieJar } from '../storage/settings';

export const jar = new CookieJar();

export const client = wrapper(
  axios.create({
    jar,
    withCredentials: true,
    timeout: 30000,
    maxRedirects: 5,
  })
);

let _baseURL = '';

export function setBaseURL(url: string) {
  _baseURL = url;
  client.defaults.baseURL = url;
}

export function getBaseURL(): string {
  return _baseURL;
}

// Persist cookie jar after every response
client.interceptors.response.use(
  async (response) => {
    try {
      await setCookieJarJson(JSON.stringify(jar.toJSON()));
    } catch {}
    return response;
  },
  async (error) => {
    try {
      await setCookieJarJson(JSON.stringify(jar.toJSON()));
    } catch {}
    return Promise.reject(error);
  }
);

export async function restoreCookieJar(): Promise<void> {
  try {
    const saved = await getCookieJarJson();
    if (!saved) return;
    const parsed = JSON.parse(saved);
    const cookies: any[] = parsed.cookies || [];
    for (const c of cookies) {
      if (c.key && c.value && c.domain) {
        const proto = c.secure ? 'https' : 'http';
        const url = `${proto}://${c.domain}${c.path || '/'}`;
        try {
          await jar.setCookie(`${c.key}=${c.value}`, url);
        } catch {}
      }
    }
  } catch {}
}

export async function clearSession(): Promise<void> {
  jar.removeAllCookiesSync();
  await clearCookieJar();
}
