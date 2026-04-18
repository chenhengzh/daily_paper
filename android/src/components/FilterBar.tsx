import React from 'react';
import { View, Text, Pressable, ScrollView, StyleSheet } from 'react-native';
import { useTheme } from '../hooks/useTheme';
import { ViewMode } from '../hooks/usePapers';

interface Props {
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  fields: string[];
  activeField: string;
  onFieldChange: (field: string) => void;
}

export function FilterBar({
  viewMode,
  onViewModeChange,
  fields,
  activeField,
  onFieldChange,
}: Props) {
  const { colors } = useTheme();

  return (
    <View>
      {/* 精选/全部 toggle */}
      <View style={[styles.segmented, { borderColor: colors.border, backgroundColor: colors.bg2 }]}>
        {(['selected', 'all'] as ViewMode[]).map((mode) => {
          const active = viewMode === mode;
          return (
            <Pressable
              key={mode}
              onPress={() => onViewModeChange(mode)}
              style={[
                styles.segment,
                active && { backgroundColor: colors.accent },
              ]}
            >
              <Text style={[styles.segmentText, { color: active ? '#fff' : colors.text2 }]}>
                {mode === 'selected' ? '精选' : '全部'}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {/* Field filter chips — only shown in selected mode */}
      {viewMode === 'selected' && fields.length > 1 && (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.chips}
        >
          {fields.map((f) => {
            const active = activeField === f;
            return (
              <Pressable
                key={f}
                onPress={() => onFieldChange(f)}
                style={[
                  styles.chip,
                  {
                    backgroundColor: active ? colors.accent : colors.bg3,
                    borderColor: active ? colors.accent : colors.border,
                  },
                ]}
              >
                <Text style={[styles.chipText, { color: active ? '#fff' : colors.text2 }]}>
                  {f}
                </Text>
              </Pressable>
            );
          })}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  segmented: {
    flexDirection: 'row',
    marginHorizontal: 16,
    marginVertical: 8,
    borderRadius: 8,
    borderWidth: 1,
    overflow: 'hidden',
    height: 34,
  },
  segment: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  segmentText: {
    fontSize: 13,
    fontWeight: '600',
  },
  chips: {
    paddingHorizontal: 16,
    paddingBottom: 8,
    gap: 6,
    flexDirection: 'row',
  },
  chip: {
    borderRadius: 14,
    borderWidth: 1,
    paddingHorizontal: 12,
    height: 28,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipText: {
    fontSize: 12,
    fontWeight: '500',
  },
});
