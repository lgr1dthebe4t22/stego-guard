// HTTP-клиент к Go-гейтвею. Запросы идут на /api/* — Vite проксирует на :8080.
import type { EmbedResult, VerifyResponse } from '../types/api';

async function parseError(resp: Response): Promise<never> {
  const data = await resp.json().catch(() => null);
  throw new Error(data?.error ?? `HTTP ${resp.status}`);
}

export async function embedDocument(file: File, userId: string): Promise<EmbedResult> {
  const fd = new FormData();
  fd.append('user_id', userId);
  fd.append('file', file);

  const resp = await fetch('/api/v1/embed', { method: 'POST', body: fd });
  if (!resp.ok) await parseError(resp);

  return {
    blob: await resp.blob(),
    sha256: resp.headers.get('X-Content-SHA256') ?? '',
    userId,
    format: (resp.headers.get('Content-Type') ?? '').includes('jpeg') ? 'jpeg' : 'png',
  };
}

export async function verifyDocument(file: File): Promise<VerifyResponse> {
  const fd = new FormData();
  fd.append('file', file);

  const resp = await fetch('/api/v1/verify', { method: 'POST', body: fd });
  if (!resp.ok) await parseError(resp);
  return (await resp.json()) as VerifyResponse;
}