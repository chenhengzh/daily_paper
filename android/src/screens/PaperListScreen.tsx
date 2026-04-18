import React, { useState } from 'react';
import {
  View, Text, FlatList, StyleSheet, Pressable,
  ActivityIndicator, Modal, TouchableOpacity, TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/RootNavigator';
import { usePapers } from '../hooks/usePapers';
import { PaperCard } from '../components/PaperCard';
import { FilterBar } from '../components/FilterBar';
import { useTheme } from '../hooks/useTheme';
import { Paper } from '../types/paper';

type Props = NativeStackScreenProps<RootStackParamList, 'Main'>;

function JobStatusBadge({ job, colors }: { job: any; colors: any }) {
  if (!job) return null;
  const statusMap: Record<string, { label: string; color: string }> = {
    pending: { label: '等待中', color: colors.text3 },
    scraping: { label: '抓取中...', color: colors.amber },
    rating: { label: `评分中 ${job.rated_count ?? 0}/${job.scrape_count ?? 0}`, color: colors.accent },
    done: { label: '完成', color: colors.green },
    failed: { label: '失败', color: colors.red },
  };
  const s = statusMap[job.status] ?? { label: job.status, color: colors.text3 };
  return (
    <Text style={[styles.jobStatus, { color: s.color }]}>{s.label}</Text>
  );
}

export function PaperListScreen({ navigation }: Props) {
  const { colors } = useTheme();
  const {
    dates, selectedDate, setSelectedDate,
    filteredPapers, fields, activeField, setActiveField,
    viewMode, setViewMode,
    allPapers, job,
    searchQuery, setSearchQuery,
    loading, error, refresh,
  } = usePapers();

  const [showDatePicker, setShowDatePicker] = useState(false);
  const [showSearch, setShowSearch] = useState(false);

  const keptCount = allPapers.filter(p => p.keep).length;
  const hpCount = allPapers.filter(p => p.high_priority).length;

  const handleCardPress = (paper: Paper) => {
    navigation.push('Detail', { paper });
  };

  const renderHeader = () => (
    <View>
      {/* App header row */}
      <View style={[styles.headerRow, { backgroundColor: colors.bg2, borderBottomColor: colors.border }]}>
        <Text style={[styles.brand, { color: colors.text }]}>📄 Daily Paper</Text>
        <View style={styles.headerRight}>
          <Pressable
            onPress={() => setShowDatePicker(true)}
            style={[styles.datePill, { backgroundColor: colors.bg3, borderColor: colors.border }]}
          >
            <Text style={[styles.datePillText, { color: colors.text2 }]}>
              {selectedDate ? selectedDate.slice(5) : '--/--'} ▾
            </Text>
          </Pressable>
          <Pressable
            onPress={() => setShowSearch(v => !v)}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Text style={[styles.iconBtn, { color: showSearch ? colors.accent : colors.text3 }]}>🔍</Text>
          </Pressable>
          <Pressable
            onPress={() => navigation.push('Settings')}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Text style={[styles.iconBtn, { color: colors.text3 }]}>⚙</Text>
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
            clearButtonMode="while-editing"
          />
        </View>
      )}

      {/* Stats + job status row */}
      <View style={[styles.statsRow, { backgroundColor: colors.bg2 }]}>
        <Text style={[styles.stat, { color: colors.text3 }]}>
          总 <Text style={{ color: colors.text }}>{allPapers.length}</Text>
        </Text>
        <Text style={[styles.stat, { color: colors.text3 }]}>
          精选 <Text style={{ color: colors.green }}>{keptCount}</Text>
        </Text>
        <Text style={[styles.stat, { color: colors.text3 }]}>
          高优 <Text style={{ color: colors.amber }}>{hpCount}</Text>
        </Text>
        {searchQuery ? (
          <Text style={[styles.stat, { color: colors.text3 }]}>
            结果 <Text style={{ color: colors.accent }}>{filteredPapers.length}</Text>
          </Text>
        ) : null}
        <View style={{ flex: 1 }} />
        <JobStatusBadge job={job} colors={colors} />
      </View>

      {/* Filter bar */}
      <FilterBar
        viewMode={viewMode}
        onViewModeChange={(m) => { setViewMode(m); setActiveField('全部'); }}
        fields={fields}
        activeField={activeField}
        onFieldChange={setActiveField}
      />
    </View>
  );

  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: colors.bg2 }}>
      {loading && allPapers.length === 0 ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.accent} size="large" />
          <Text style={[styles.loadingText, { color: colors.text3 }]}>加载中...</Text>
        </View>
      ) : error ? (
        <View style={styles.center}>
          <Text style={[styles.errorText, { color: colors.red }]}>{error}</Text>
          <Pressable onPress={refresh} style={[styles.retryBtn, { borderColor: colors.border }]}>
            <Text style={{ color: colors.accent }}>重试</Text>
          </Pressable>
        </View>
      ) : (
        <FlatList
          data={filteredPapers}
          keyExtractor={(p) => p.arxiv_id}
          renderItem={({ item }) => (
            <PaperCard paper={item} onPress={() => handleCardPress(item)} />
          )}
          ListHeaderComponent={renderHeader}
          contentContainerStyle={styles.list}
          ItemSeparatorComponent={() => <View style={{ height: 8 }} />}
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Text style={[styles.emptyText, { color: colors.text3 }]}>
                {searchQuery ? `"${searchQuery}" 无匹配结果` : '暂无论文'}
              </Text>
              {searchQuery ? (
                <Pressable onPress={() => setSearchQuery('')}>
                  <Text style={{ color: colors.accent, marginTop: 8 }}>清除搜索</Text>
                </Pressable>
              ) : null}
            </View>
          }
          initialNumToRender={8}
          maxToRenderPerBatch={8}
          windowSize={5}
          removeClippedSubviews
          onRefresh={refresh}
          refreshing={loading}
        />
      )}

      {/* Date picker modal */}
      <Modal
        visible={showDatePicker}
        transparent
        animationType="fade"
        onRequestClose={() => setShowDatePicker(false)}
      >
        <TouchableOpacity
          style={styles.modalOverlay}
          activeOpacity={1}
          onPress={() => setShowDatePicker(false)}
        >
          <View style={[styles.datePicker, { backgroundColor: colors.bg3, borderColor: colors.border }]}>
            <Text style={[styles.datePickerTitle, { color: colors.text2 }]}>选择日期</Text>
            {dates.map((d) => (
              <Pressable
                key={d}
                onPress={() => { setSelectedDate(d); setShowDatePicker(false); }}
                style={({ pressed }) => [
                  styles.dateItem,
                  {
                    backgroundColor: d === selectedDate
                      ? colors.accentLight
                      : pressed ? colors.bgPressed : 'transparent',
                  },
                ]}
              >
                <Text style={[
                  styles.dateItemText,
                  { color: d === selectedDate ? colors.accent : colors.text },
                ]}>
                  {d}
                </Text>
              </Pressable>
            ))}
          </View>
        </TouchableOpacity>
      </Modal>
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
  datePill: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    borderWidth: 1,
  },
  datePillText: { fontSize: 13, fontWeight: '500' },
  iconBtn: { fontSize: 18 },
  searchRow: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  searchInput: {
    height: 38,
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: 12,
    fontSize: 14,
  },
  statsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 16,
    paddingVertical: 6,
  },
  stat: { fontSize: 12 },
  jobStatus: { fontSize: 11, fontWeight: '500' },
  list: { paddingHorizontal: 16, paddingBottom: 24, paddingTop: 4 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32, gap: 12 },
  loadingText: { fontSize: 14 },
  errorText: { fontSize: 14, textAlign: 'center' },
  emptyContainer: { alignItems: 'center', paddingTop: 60 },
  emptyText: { fontSize: 14 },
  retryBtn: { borderWidth: 1, borderRadius: 8, paddingHorizontal: 16, paddingVertical: 8 },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.6)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  datePicker: {
    width: 260,
    borderRadius: 12,
    borderWidth: 1,
    padding: 8,
    maxHeight: 400,
  },
  datePickerTitle: {
    fontSize: 12,
    fontWeight: '600',
    textAlign: 'center',
    paddingVertical: 8,
  },
  dateItem: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 8,
  },
  dateItemText: { fontSize: 14 },
});
