import { useEffect, useState } from 'react';
import { list, STORAGE_KEY, subscribe, type StoredMeetingSummary } from '../lib/meetingsRegistry';

export function useMeetingsRegistry(): StoredMeetingSummary[] {
  const [entries, setEntries] = useState<StoredMeetingSummary[]>(() => list());

  useEffect(() => {
    const refresh = () => setEntries(list());
    const unsub = subscribe(refresh);
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY || e.key === null) refresh();
    };
    window.addEventListener('storage', onStorage);
    return () => {
      unsub();
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  return entries;
}
