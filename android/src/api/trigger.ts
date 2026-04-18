import { client } from './client';

export async function triggerPipeline(force = false): Promise<void> {
  await client.post('/papers/trigger', { force });
}

export async function getTriggerStatus(): Promise<{ running: boolean }> {
  const { data } = await client.get<{ running: boolean }>('/papers/trigger/status');
  return data;
}
