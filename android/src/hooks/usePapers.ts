import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchDates, fetchPapers } from '../api/papers';
import { Paper } from '../types/paper';

export type ViewMode = 'selected' | 'all';

export function useDates() {
  return useQuery({
    queryKey: ['dates'],
    queryFn: fetchDates,
    staleTime: 60_000,
  });
}

export function usePapers() {
  const datesQuery = useDates();
  const dates = datesQuery.data ?? [];

  const [selectedDate, setSelectedDate] = useState<string>('');
  const [viewMode, setViewMode] = useState<ViewMode>('selected');
  const [activeField, setActiveField] = useState<string>('全部');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Use first available date as default
  const effectiveDate = selectedDate || dates[0] || '';

  const papersQuery = useQuery({
    queryKey: ['papers', effectiveDate],
    queryFn: () => fetchPapers(effectiveDate),
    enabled: !!effectiveDate,
    staleTime: 120_000,
  });

  const allPapers: Paper[] = papersQuery.data?.papers ?? [];
  const job = papersQuery.data?.job ?? null;

  const fields = ['全部', ...Array.from(
    new Set(allPapers.filter(p => p.keep && p.interest_field).map(p => p.interest_field!))
  )];

  const filteredPapers = allPapers.filter(p => {
    if (viewMode === 'selected' && !p.keep) return false;
    if (viewMode === 'selected' && activeField !== '全部' && p.interest_field !== activeField) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const hit = (p.title || '').toLowerCase().includes(q) ||
        (p.tldr_zh || '').toLowerCase().includes(q) ||
        (p.tldr || '').toLowerCase().includes(q) ||
        (p.summary || '').toLowerCase().includes(q);
      if (!hit) return false;
    }
    return true;
  });

  return {
    dates,
    selectedDate: effectiveDate,
    setSelectedDate,
    allPapers,
    filteredPapers,
    fields,
    activeField,
    setActiveField,
    viewMode,
    setViewMode,
    searchQuery,
    setSearchQuery,
    job,
    loading: papersQuery.isLoading || datesQuery.isLoading,
    error: papersQuery.error?.message || datesQuery.error?.message || null,
    refresh: () => papersQuery.refetch(),
  };
}
