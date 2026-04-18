import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { useTheme } from '../hooks/useTheme';

interface Props {
  label: string;
  score: number | null;
  primary?: boolean;
}

export function ScoreBar({ label, score, primary = false }: Props) {
  const { colors } = useTheme();
  if (score == null) return null;

  const pct = Math.min(100, Math.max(0, (score / 10) * 100));
  const color =
    score >= 8.0 ? colors.scoreHigh :
    score >= 6.0 ? colors.scoreMid :
    score >= 4.0 ? colors.scoreLow :
    colors.scoreBad;

  const barH = primary ? 6 : 4;

  return (
    <View style={styles.row}>
      <Text style={[styles.label, { color: colors.text2, width: primary ? 60 : 72 }]}>
        {label}
      </Text>
      <View style={[styles.track, { backgroundColor: colors.bgInput, height: barH, flex: 1 }]}>
        <View style={[styles.fill, { width: `${pct}%`, backgroundColor: color, height: barH }]} />
      </View>
      <Text style={[styles.value, { color, width: 32 }]}>
        {score.toFixed(1)}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 6,
  },
  label: {
    fontSize: 12,
  },
  track: {
    borderRadius: 3,
    overflow: 'hidden',
  },
  fill: {
    borderRadius: 3,
  },
  value: {
    fontSize: 12,
    fontWeight: '600',
    fontVariant: ['tabular-nums'],
    textAlign: 'right',
  },
});
