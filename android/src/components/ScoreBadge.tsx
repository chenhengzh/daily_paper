import React from 'react';
import { Text, View, StyleSheet } from 'react-native';
import { useTheme } from '../hooks/useTheme';

interface Props {
  score: number | null;
  size?: 'sm' | 'md';
}

export function ScoreBadge({ score, size = 'md' }: Props) {
  const { colors } = useTheme();

  if (score == null) return null;

  const color =
    score >= 8.0 ? colors.scoreHigh :
    score >= 6.0 ? colors.scoreMid :
    score >= 4.0 ? colors.scoreLow :
    colors.scoreBad;

  const fontSize = size === 'sm' ? 11 : 13;
  const minWidth = size === 'sm' ? 30 : 36;

  return (
    <View style={[styles.badge, { borderColor: color, minWidth }]}>
      <Text style={[styles.text, { color, fontSize }]}>
        {score.toFixed(1)}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    borderWidth: 1,
    borderRadius: 6,
    paddingHorizontal: 5,
    paddingVertical: 1,
    alignItems: 'center',
  },
  text: {
    fontWeight: '700',
    fontVariant: ['tabular-nums'],
  },
});
