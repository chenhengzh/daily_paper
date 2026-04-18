import React from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { Paper } from '../types/paper';
import { useTheme } from '../hooks/useTheme';
import { TagChip } from './TagChip';
import { ScoreBadge } from './ScoreBadge';

interface Props {
  paper: Paper;
  onPress: () => void;
  bookmarked?: boolean;
  onBookmark?: () => void;
}

export function PaperCard({ paper, onPress, bookmarked, onBookmark }: Props) {
  const { colors } = useTheme();
  const isHP = paper.high_priority;
  const isFiltered = !paper.keep;

  const authors = paper.authors.slice(0, 3).join(', ') +
    (paper.authors.length > 3 ? ` +${paper.authors.length - 3}` : '');

  const dateStr = paper.published_date ? paper.published_date.slice(0, 10) : '';

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.card,
        {
          backgroundColor: isHP ? colors.bgHP : colors.bg3,
          borderLeftWidth: isHP ? 2 : 0,
          borderLeftColor: colors.amber,
          borderColor: colors.border,
          opacity: pressed ? 0.85 : isFiltered ? 0.45 : 1,
        },
      ]}
    >
      {/* Header row: hp badge + field chip + score + bookmark */}
      <View style={styles.headerRow}>
        <View style={styles.headerLeft}>
          {isHP && (
            <Text style={[styles.hpBadge, { color: colors.amber }]}>
              ⭐ #{paper.high_priority_rank}
            </Text>
          )}
          {paper.interest_field ? (
            <TagChip label={paper.interest_field} />
          ) : null}
        </View>
        <View style={styles.headerRight}>
          <ScoreBadge score={paper.overall_priority_score} />
          {onBookmark && (
            <Pressable
              onPress={(e) => { e.stopPropagation(); onBookmark(); }}
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
            >
              <Text style={[styles.bookmarkIcon, { color: bookmarked ? colors.accent : colors.text3 }]}>
                {bookmarked ? '🔖' : '📑'}
              </Text>
            </Pressable>
          )}
        </View>
      </View>

      {/* Title */}
      <Text style={[styles.title, { color: colors.text }]} numberOfLines={2}>
        {paper.title}
      </Text>

      {/* Authors + date */}
      <View style={styles.metaRow}>
        <Text style={[styles.meta, { color: colors.text3, flex: 1 }]} numberOfLines={1}>
          {authors}
        </Text>
        {dateStr ? (
          <Text style={[styles.meta, { color: colors.text3 }]}>{dateStr}</Text>
        ) : null}
      </View>

      {/* TLDR */}
      {(paper.tldr_zh || paper.tldr) ? (
        <Text style={[styles.tldr, { color: colors.text2 }]} numberOfLines={2}>
          {paper.tldr_zh || paper.tldr}
        </Text>
      ) : null}

      {/* Footer: tags */}
      <View style={styles.footer}>
        <View style={styles.tags}>
          {paper.tags.slice(0, 3).map((t) => (
            <TagChip key={t} label={t} />
          ))}
        </View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 10,
    borderWidth: 1,
    padding: 12,
    gap: 6,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    flex: 1,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  hpBadge: {
    fontSize: 12,
    fontWeight: '700',
  },
  bookmarkIcon: {
    fontSize: 16,
  },
  title: {
    fontSize: 15,
    fontWeight: '600',
    lineHeight: 21,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  meta: {
    fontSize: 12,
  },
  tldr: {
    fontSize: 13,
    lineHeight: 19,
  },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 2,
  },
  tags: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 4,
    flex: 1,
  },
});
