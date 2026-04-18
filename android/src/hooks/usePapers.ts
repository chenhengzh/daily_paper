import { useState, useEffect, useCallback } from 'react';
import { fetchDates, fetchPapers } from '../api/papers';
import { Paper, DailyJob } from '../types/paper';

export type ViewMode = 'selected' | 'all';

export function usePapers() {
  const [dates, setDates] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>('');
  const [allPapers, setAllPapers] = useState<Paper[]>([]);
  const [job, setJob] = useState<DailyJob | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('selected');
  const [activeField, setActiveField] = useState<string>('全部');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDates = useCallback(async () => {
    try {
      const d = await fetchDates();
      setDates(d);
      if (d.length > 0) setSelectedDate(d[0]);
    } catch (e: any) {
      setError(e?.message || 'Failed to load dates');
    }
  }, []);

  const loadPapers = useCallback(async (date: string) => {
    if (!date) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetchPapers(date);
      setAllPapers(res.papers || []);
      setJob(res.job);
    } catch (e: any) {
      setError(e?.message || 'Failed to load papers');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDates();
  }, [loadDates]);

  useEffect(() => {
    if (selectedDate) loadPapers(selectedDate);
  }, [selectedDate, loadPapers]);

  const fields = ['全部', ...Array.from(
    new Set(allPapers.filter(p => p.keep && p.interest_field).map(p => p.interest_field!))
  )];

  const filteredPapers = allPapers.filter(p => {
    if (viewMode === 'selected' && !p.keep) return false;
    if (viewMode === 'selected' && activeField !== '全部' && p.interest_field !== activeField) return false;
    return true;
  });

  return {
    dates,
    selectedDate,
    setSelectedDate,
    allPapers,
    filteredPapers,
    fields,
    activeField,
    setActiveField,
    viewMode,
    setViewMode,
    job,
    loading,
    error,
    refresh: () => loadPapers(selectedDate),
  };
}
