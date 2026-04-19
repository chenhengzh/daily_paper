import { client, clearSession } from './client';

export async function login(username: string, password: string): Promise<void> {
  const body = new URLSearchParams();
  body.append('username', username);
  body.append('password', password);

  // Server returns 303 redirect on success; we accept 2xx and 3xx as success.
  // Cookie is captured by the response interceptor in client.ts.
  const response = await client.post('/auth/login', body.toString(), {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    validateStatus: (status) => status < 500,
  });

  // 401/403 means wrong credentials
  if (response.status === 401 || response.status === 403) {
    throw new Error('用户名或密码错误');
  }
}

export async function logout(): Promise<void> {
  try {
    await client.post('/auth/logout');
  } catch {}
  await clearSession();
}
