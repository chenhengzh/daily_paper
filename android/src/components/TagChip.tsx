import React from 'react';
import { Text, View, StyleSheet } from 'react-native';
import { useTheme } from '../hooks/useTheme';

interface Props {
  label: string;
  variant?: 'default' | 'green' | 'amber';
}

export function TagChip({ label, variant = 'default' }: Props) {
  const { colors } = useTheme();

  const bg =
    variant === 'green' ? colors.greenLight :
    variant === 'amber' ? colors.amberLight :
    colors.tagBg;

  const textColor =
    variant === 'green' ? colors.green :
    variant === 'amber' ? colors.amber :
    colors.tagText;

  return (
    <View style={[styles.chip, { backgroundColor: bg }]}>
      <Text style={[styles.text, { color: textColor }]} numberOfLines={1}>
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    borderRadius: 10,
    paddingHorizontal: 8,
    paddingVertical: 2,
    alignSelf: 'flex-start',
  },
  text: {
    fontSize: 11,
    fontWeight: '600',
  },
});
