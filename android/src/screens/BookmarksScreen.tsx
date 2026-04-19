import React, { useState, useCallback } from 'react';
import {
  View, Text, FlatList, StyleSheet, Pressable,
  ActivityIndicator, TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { RootStackParamList } from '../navigation/RootNavigator';
import { fetchBookmarksFull, bookmarkPaper, unbookmarkPaper } from '../api/papers';
import { PaperCard } from '../components/PaperCard';
import { useTheme } from '../hooks/useTheme';
import { Paper } from '../types/paper';

type Props = NativeStackScreenProps<RootStackParamList, 'Bookmarks'>;

export function BookmarksScreen({ navigation }: Props) {
  const { colors } = useTheme();
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');
  const [activeField, setActiveField] = useState('全部');
  const [showSearch, setShowSearch] = useState(false);

  const { data: papers = [], isLoading, error, refetch } = useQuery({
    queryKey: ['bookmarks'],
    queryFn: fetchBookmarksFull,
    staleTime: 0,
  });

  const handleToggleBookmark = useCallback(async (arxivId: string) => {
    const paper = papers.find(p => p.arxiv_id === arxivId);
    if (!paper) return;
    try {
      await unbookmarkPaper(arxivId);
      queryClient.setQueryData<Paper[]>(['bookmarks'], (old = []) =>
        old.filter(p => p.arxiv_id !== arxivId)
      );
    } catch {}
  }, [papers, queryClient]);

  const fields = ['全部', ...Array.from(
    new Set(papers.filter(p => p.interest_field).map(p => p.interest_field!))
  )];

  const filtered = papers.filter(p => {
    if (activeField !== '全部' && p.interest_field !== activeField) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return (p.title || '').toLowerCase().includes(q) ||
        (p.tldr_zh || '').toLowerCase().includes(q) ||
        (p.tldr || '').toLowerCase().includes(q);
    }
    return true;
  });

  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: colors.bg2 }}>
      {/* Header */}
      <View style={[styles.headerRow, { backgroundColor: colors.bg2, borderBottomColor: colors.border }]}>
        <Text style={[styles.brand, { color: colors.text }]}>🔖 收藏夹</Text>
        <View style={styles.headerRight}>
          <Pressable
            onPress={() => setShowSearch(v => !v)}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Text style={[styles.iconBtn, { color: showSearch ? colors.accent : colors.text3 }]}>🔍</Text>
          </Pressable>
        </View>
      </View>

      {/* Search bar */}
      {showSearch && (
        <View style={[styles.searchRow, { backgroundColor: colors.bg2, borderBottomColor: colors.border }]}>
          <TextInput
            style={[styles.searchInput, { backgroundColor: colors.bgInput, borderColor: colors.border, color: colors.text }]}
            value={searchQuery}
            onChangeText={setSearchQuery}
            placeholder="搜索标题、摘要..."
            placeholderTextColor={colors.text3}
            autoFocus
            returnKeyType="search"
          />
          {searchQuery ? (
            <Pressable onPress={() => setSearchQuery('')} style={styles.clearBtn}>
              <Text style={{ color: colors.text3 }}>✕</Text>
            </Pressable>
          ) : null}
        </View>
      )}

      {/* Stats row */}
      <View style={[styles.statsRow, { backgroundColor: colors.bg2 }]}>
        <Text style={[styles.stat, { color: colors.text3 }]}>
          收藏 <Text style={{ color: colors.accent }}>{papers.length}</Text>
        </Text>
        {searchQuery || activeField !== '全部' ? (
          <Text style={[styles.stat, { color: colors.text3 }]}>
            显示 <Text style={{ color: colors.text }}>{filtered.length}</Text>
          </Text>
        ) : null}
      </View>

      {/* Field chips */}
      {fields.length > 1 && (
        <View style={[styles.chipsRow, { borderBottomColor: colors.border }]}>
          <FlatList
            horizontal
            data={fields}
            keyExtractor={f => f}
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.chips}
            renderItem={({ item: f }) => {
              const active = activeField === f;
              return (
                <Pressable
                  onPress={() => setActiveField(f)}
                  style={[styles.chip, {
                    backgroundColor: active ? colors.accent : colors.bg3,
                    borderColor: active ? colors.accent : colors.border,
                  }]}
                >
                  <Text style={[styles.chipText, { color: active ? '#fff' : colors.text2 }]}>{f}</Text>
                </Pressable>
              );
            }}
          />
        </View>
      )}

      {isLoading ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.accent} size="large" />
          <Text style={[styles.hint, { color: colors.text3 }]}>加载中...</Text>
        </View>
      ) : error ? (
        <View style={styles.center}>
          <Text style={[styles.hint, { color: colors.red }]}>加载失败</Text>
          <Pressable onPress={() => refetch()} style={[styles.retryBtn, { borderColor: colors.border }]}>
            <Text style={{ color: colors.accent }}>重试</Text>
          </Pressable>
        </View>
      ) : (
        <FlatList
          data={filtered}
          keyExtractor={p => p.arxiv_id}
          renderItem={({ item }) => (
            <PaperCard
              paper={item}
              onPress={() => navigation.push('Detail', { paper: item })}
              bookmarked
              onBookmark={() => handleToggleBookmark(item.arxiv_id)}
            />
          )}
          contentContainerStyle={styles.list}
          ItemSeparatorComponent={() => <View style={{ height: 8 }} />}
          ListEmptyComponent={
            <View style={styles.center}>
              <Text style={[styles.hint, { color: colors.text3 }]}>
                {papers.length === 0 ? '暂无收藏' : '无匹配结果'}
              </Text>
            </View>
          }
          onRefresh={refetch}
          refreshing={isLoading}
          initialNumToRender={10}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    height: 52,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  brand: { fontSize: 17, fontWeight: '700' },
  headerRight: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  iconBtn: { fontSize: 18 },
  searchRow: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  searchInput: {
    flex: 1,
    height: 38,
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: 12,
    fontSize: 14,
  },
  clearBtn: { padding: 4 },
  statsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 16,
    paddingVertical: 6,
  },
  stat: { fontSize: 12 },
  chipsRow: { borderBottomWidth: StyleSheet.hairlineWidth },
  chips: { paddingHorizontal: 16, paddingVertical: 8, gap: 6, flexDirection: 'row' },
  chip: {
    borderRadius: 14,
    borderWidth: 1,
    paddingHorizontal: 12,
    height: 28,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipText: { fontSize: 12, fontWeight: '500' },
  list: { paddingHorizontal: 16, paddingTop: 4, paddingBottom: 24 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingTop: 60, gap: 12 },
  hint: { fontSize: 14 },
  retryBtn: { borderWidth: 1, borderRadius: 8, paddingHorizontal: 16, paddingVertical: 8 },
});
