import type { Snapshot } from './types';

export function validSnapshot(value: unknown): value is Snapshot {
  if (!value || typeof value !== 'object') return false;
  const d = value as Snapshot;
  return d.schema_version === 1 && Array.isArray(d.papers) && !!d.coverage && d.coverage.total === d.papers.length
    && Number.isFinite(Date.parse(d.generated_at)) && Array.isArray(d.sources) && !!d.schedule
    && d.papers.every(p => !!p.title && /^10\.\d{4,9}\//.test(p.doi) && /^\d{4}-\d{2}-\d{2}$/.test(p.date)
      && Array.isArray(p.authors) && Array.isArray(p.topics) && Array.isArray(p.provenance)
      && [p.accesses?.value,p.citations?.value].every(n => n === null || (Number.isSafeInteger(n) && n! >= 0)));
}

async function cache(mode: 'read' | 'write', snapshot?: Snapshot): Promise<Snapshot | null> {
  try {
    const db = await new Promise<IDBDatabase>((resolve,reject) => {
      const request = indexedDB.open('neuro-paper-radar',1);
      request.onupgradeneeded = () => request.result.createObjectStore('snapshots');
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    return await new Promise<Snapshot | null>((resolve,reject) => {
      const tx = db.transaction('snapshots', mode === 'write' ? 'readwrite' : 'readonly');
      const store = tx.objectStore('snapshots');
      const request = mode === 'write' ? store.put(snapshot,'last-good') : store.get('last-good');
      let result: Snapshot | null = null;
      request.onsuccess = () => { result = mode === 'read' && validSnapshot(request.result) ? request.result : snapshot || null; };
      tx.oncomplete = () => { db.close(); resolve(result); };
      tx.onerror = () => { db.close(); reject(tx.error); };
      tx.onabort = () => { db.close(); reject(tx.error); };
    });
  } catch { return null; }
}

export async function loadSnapshot(previous: Snapshot | null = null): Promise<{ data: Snapshot | null; cached: boolean }> {
  try {
    const response = await fetch(import.meta.env.BASE_URL + 'data/papers.json', { cache:'no-cache', signal: AbortSignal.timeout(20000) });
    if (!response.ok) throw new Error('Data response failed');
    const data: unknown = await response.json();
    if (!validSnapshot(data)) throw new Error('Invalid data snapshot');
    await cache('write',data);
    return { data, cached:false };
  } catch {
    return { data: previous || await cache('read'), cached:true };
  }
}
