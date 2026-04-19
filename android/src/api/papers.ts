import { client } from './client';
import { Paper, PapersResponse } from '../types/paper';

export async function fetchDates(): Promise<string[]> {
  const { data } = await client.get<string[]>('/papers/dates');
  return Array.isArray(data) ? data : [];
}

export async function fetchPapers(date: string): Promise<PapersResponse> {
  const { data } = await client.get<PapersResponse>('/papers/api', {
    params: { date },
  });
  return data;
}

export async function fetchPaper(arxivId: string): Promise<Paper> {
  const { data } = await client.get<Paper>(`/papers/${arxivId}`);
  return data;
}

export async function bookmarkPaper(arxivId: string): Promise<void> {
  await client.post(`/papers/${arxivId}/bookmark`);
}

export async function unbookmarkPaper(arxivId: string): Promise<void> {
  await client.delete(`/papers/${arxivId}/bookmark`);
}
