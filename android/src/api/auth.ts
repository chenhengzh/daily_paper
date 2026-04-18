import { client, clearSession } from './client';

export async function login(username: string, password: string): Promise<void> {
  const body = new URLSearchParams();
  body.append('username', username);
  body.append('password', password);

  // Server returns 303 redirect to /papers/ on success; axios follows it.
  // The dp_session cookie is captured by tough-cookie before the redirect.
  await client.post('/auth/login', body.toString(), {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    validateStatus: (status) => status < 500,
  });
}

export async function logout(): Promise<void> {
  try {
    await client.post('/auth/logout');
  } catch {}
  await clearSession();
}
