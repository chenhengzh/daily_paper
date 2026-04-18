import React, { useState } from 'react';
import {
  View, Text, FlatList, StyleSheet, Pressable,
  ActivityIndicator, Modal, TouchableOpacity,
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

export function PaperListScreen({ navigation }: Props) {
  const { colors } = useTheme();
  const {
    dates, selectedDate, setSelectedDate,
    filteredPapers, fields, activeField, setActiveField,
    viewMode, setViewMode,
    allPapers, job,
    loading, error, refresh,
  } = usePapers();

  const [showDatePicker, setShowDatePicker] = useState(false);

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
            onPress={() => navigation.push('Settings')}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Text style={[styles.settingsIcon, { color: colors.text3 }]}>⚙</Text>
          </Pressable>
        </View>
      </View>

      {/* Stats row */}
      {allPapers.length > 0 && (
        <View style={[styles.statsRow, { backgroundColor: colors.bg2 }]}>
          <Text style={[styles.stat, { color: colors.text3 }]}>总计 <Text style={{ color: colors.text }}>{allPapers.length}</Text></Text>
          <Text style={[styles.stat, { color: colors.text3 }]}>精选 <Text style={{ color: colors.green }}>{keptCount}</Text></Text>
          <Text style={[styles.stat, { color: colors.text3 }]}>高优 <Text style={{ color: colors.amber }}>{hpCount}</Text></Text>
        </View>
      )}

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
            <View style={styles.center}>
              <Text style={[styles.emptyText, { color: colors.text3 }]}>暂无论文</Text>
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
  headerRight: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  datePill: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    borderWidth: 1,
  },
  datePillText: { fontSize: 13, fontWeight: '500' },
  settingsIcon: { fontSize: 20 },
  statsRow: {
    flexDirection: 'row',
    gap: 16,
    paddingHorizontal: 16,
    paddingVertical: 6,
  },
  stat: { fontSize: 12 },
  list: { paddingHorizontal: 16, paddingBottom: 24, paddingTop: 4 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32, gap: 12 },
  loadingText: { fontSize: 14 },
  errorText: { fontSize: 14, textAlign: 'center' },
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
