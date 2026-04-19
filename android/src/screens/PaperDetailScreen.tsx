import React, { useState } from 'react';
import {
  View, Text, ScrollView, StyleSheet, Pressable,
  LayoutAnimation, UIManager, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import * as Linking from 'expo-linking';
import { RootStackParamList } from '../navigation/RootNavigator';
import { TagChip } from '../components/TagChip';
import { ScoreBar } from '../components/ScoreBar';
import { useTheme } from '../hooks/useTheme';
import { bookmarkPaper, unbookmarkPaper } from '../api/papers';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

type Props = NativeStackScreenProps<RootStackParamList, 'Detail'>;

function SectionDivider({ label, colors }: { label: string; colors: any }) {
  return (
    <View style={[divStyles.row, { borderBottomColor: colors.border }]}>
      <Text style={[divStyles.label, { color: colors.text3 }]}>{label}</Text>
    </View>
  );
}

const divStyles = StyleSheet.create({
  row: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    paddingBottom: 6,
    marginBottom: 10,
    marginTop: 20,
  },
  label: { fontSize: 11, fontWeight: '600', letterSpacing: 0.8, textTransform: 'uppercase' },
});

export function PaperDetailScreen({ route, navigation }: Props) {
  const { colors } = useTheme();
  const { paper } = route.params;
  const [abstractExpanded, setAbstractExpanded] = useState(false);
  const [bookmarked, setBookmarked] = useState(paper.is_bookmarked ?? false);

  const handleBookmark = async () => {
    const next = !bookmarked;
    setBookmarked(next);
    try {
      if (next) {
        await bookmarkPaper(paper.arxiv_id);
      } else {
        await unbookmarkPaper(paper.arxiv_id);
      }
    } catch {
      setBookmarked(!next); // revert on failure
    }
  };

  const toggleAbstract = () => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setAbstractExpanded((v) => !v);
  };

  const openAlphaXiv = () => {
    Linking.openURL(`https://alphaxiv.org/abs/${paper.arxiv_id}`);
  };

  const openPDF = () => {
    if (paper.pdf_url) Linking.openURL(paper.pdf_url);
  };

  const authors = paper.authors.slice(0, 5).join(', ') +
    (paper.authors.length > 5 ? ` 等${paper.authors.length}人` : '');
  const dateStr = paper.published_date ? paper.published_date.slice(0, 10) : '';

  return (
    <SafeAreaView edges={['bottom']} style={{ flex: 1, backgroundColor: colors.bg }}>
      <ScrollView
        contentContainerStyle={[styles.container, { paddingBottom: 40 }]}
        showsVerticalScrollIndicator={false}
      >
        {/* High priority badge */}
        {paper.high_priority && (
          <View style={[styles.hpBadge, { backgroundColor: colors.amberLight }]}>
            <Text style={[styles.hpText, { color: colors.amber }]}>
              ⭐ HIGH PRIORITY #{paper.high_priority_rank}
            </Text>
          </View>
        )}

        {/* Title */}
        <Text style={[styles.title, { color: colors.text }]} selectable>
          {paper.title}
        </Text>

        {/* Tags */}
        <View style={styles.tagRow}>
          {paper.interest_field && <TagChip label={paper.interest_field} />}
          {paper.interest_subfield && paper.interest_subfield !== paper.interest_field && (
            <TagChip label={paper.interest_subfield} />
          )}
          {paper.tags.slice(0, 4).map((t) => <TagChip key={t} label={t} />)}
        </View>

        {/* Authors + date */}
        <Text style={[styles.meta, { color: colors.text3 }]} numberOfLines={2}>
          {authors}
          {dateStr ? `  ·  ${dateStr}` : ''}
        </Text>

        {/* Action buttons */}
        <View style={styles.btnRow}>
          <Pressable
            onPress={openAlphaXiv}
            style={({ pressed }) => [
              styles.btn,
              { backgroundColor: colors.accent, opacity: pressed ? 0.8 : 1, flex: 1 },
            ]}
          >
            <Text style={styles.btnText}>alphaXiv ↗</Text>
          </Pressable>
          {paper.pdf_url && (
            <Pressable
              onPress={openPDF}
              style={({ pressed }) => [
                styles.btn,
                { backgroundColor: colors.bg3, borderWidth: 1, borderColor: colors.border, opacity: pressed ? 0.8 : 1, flex: 1 },
              ]}
            >
              <Text style={[styles.btnText, { color: colors.text }]}>PDF ↗</Text>
            </Pressable>
          )}
          <Pressable
            onPress={handleBookmark}
            style={({ pressed }) => [
              styles.btn,
              styles.btnSquare,
              { backgroundColor: bookmarked ? colors.accentLight : colors.bg3, borderWidth: 1, borderColor: bookmarked ? colors.accent : colors.border, opacity: pressed ? 0.8 : 1 },
            ]}
          >
            <Text style={{ fontSize: 20 }}>{bookmarked ? '🔖' : '📑'}</Text>
          </Pressable>
        </View>

        {/* TLDR */}
        {(paper.tldr_zh || paper.tldr) && (
          <>
            <SectionDivider label="TLDR" colors={colors} />
            <Text style={[styles.tldr, { color: colors.text }]}>
              {paper.tldr_zh || paper.tldr}
            </Text>
          </>
        )}

        {/* Scores */}
        <SectionDivider label="评分" colors={colors} />
        <ScoreBar label="Overall" score={paper.overall_priority_score} primary />
        <ScoreBar label="Relevance" score={paper.relevance_score} />
        <ScoreBar label="Quality" score={paper.quality_score} />
        <ScoreBar label="Novelty" score={paper.novelty_claim_score} />
        <ScoreBar label="Impact" score={paper.impact_score} />

        {/* Chinese summary */}
        {paper.summary_zh && (
          <>
            <SectionDivider label="中文摘要" colors={colors} />
            <Text style={[styles.body, { color: colors.text2 }]} selectable>
              {paper.summary_zh}
            </Text>
          </>
        )}

        {/* Signal keywords */}
        {paper.signal_high_keywords?.length > 0 && (
          <>
            <SectionDivider label="信号关键词" colors={colors} />
            <View style={styles.tagRow}>
              {paper.signal_high_keywords.map((k) => (
                <TagChip key={k} label={k} variant="green" />
              ))}
            </View>
          </>
        )}

        {/* Collapsible English abstract */}
        <SectionDivider label="原文摘要" colors={colors} />
        <Pressable onPress={toggleAbstract} style={styles.collapseToggle}>
          <Text style={[styles.collapseText, { color: colors.accent }]}>
            {abstractExpanded ? '▾ 收起' : '▸ 展开英文原文'}
          </Text>
        </Pressable>
        {abstractExpanded && (
          <Text style={[styles.abstract, { color: colors.text3 }]} selectable>
            {paper.summary}
          </Text>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    padding: 16,
  },
  hpBadge: {
    alignSelf: 'flex-start',
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 3,
    marginBottom: 10,
  },
  hpText: { fontSize: 11, fontWeight: '700', letterSpacing: 0.5 },
  title: { fontSize: 20, fontWeight: '700', lineHeight: 28, marginBottom: 10 },
  tagRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 8 },
  meta: { fontSize: 12, lineHeight: 18, marginBottom: 14 },
  btnRow: { flexDirection: 'row', gap: 10, marginBottom: 4 },
  btn: {
    height: 48,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  btnSquare: {
    flex: 0,
    width: 48,
  },
  btnText: { color: '#fff', fontSize: 14, fontWeight: '600' },
  tldr: { fontSize: 15, lineHeight: 23 },
  body: { fontSize: 14, lineHeight: 22 },
  collapseToggle: { paddingVertical: 4 },
  collapseText: { fontSize: 13, fontWeight: '500' },
  abstract: { fontSize: 13, lineHeight: 20, marginTop: 8 },
});
