import React, { useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, Pressable, TextInput,
  Alert, ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/RootNavigator';
import { getServerUrl, setServerUrl, ThemePref } from '../storage/settings';
import { setBaseURL } from '../api/client';
import { logout } from '../api/auth';
import { useTheme } from '../hooks/useTheme';

type Props = NativeStackScreenProps<RootStackParamList, 'Settings'>;

function SectionHeader({ label, colors }: { label: string; colors: any }) {
  return (
    <Text style={[styles.sectionHeader, { color: colors.text3 }]}>{label}</Text>
  );
}

function SettingsRow({ label, value, onPress, colors }: {
  label: string; value?: string; onPress?: () => void; colors: any;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.row,
        { backgroundColor: pressed && onPress ? colors.bgPressed : colors.bg3, borderColor: colors.border },
      ]}
    >
      <View style={{ flex: 1 }}>
        <Text style={[styles.rowLabel, { color: colors.text }]}>{label}</Text>
        {value ? <Text style={[styles.rowValue, { color: colors.text3 }]} numberOfLines={1}>{value}</Text> : null}
      </View>
      {onPress && <Text style={[styles.chevron, { color: colors.text3 }]}>›</Text>}
    </Pressable>
  );
}

export function SettingsScreen({ navigation }: Props) {
  const { colors, themePref, setTheme } = useTheme();
  const [serverUrl, setServerUrlState] = useState('');
  const [editingUrl, setEditingUrl] = useState(false);
  const [urlInput, setUrlInput] = useState('');

  useEffect(() => {
    getServerUrl().then((u) => setServerUrlState(u || ''));
  }, []);

  const handleSaveUrl = async () => {
    const trimmed = urlInput.trim().replace(/\/$/, '');
    if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://')) {
      Alert.alert('格式错误', '地址必须以 http:// 或 https:// 开头');
      return;
    }
    await setServerUrl(trimmed);
    setBaseURL(trimmed);
    setServerUrlState(trimmed);
    setEditingUrl(false);
  };

  const handleLogout = () => {
    Alert.alert('退出登录', '确定要退出登录吗？', [
      { text: '取消', style: 'cancel' },
      {
        text: '退出',
        style: 'destructive',
        onPress: async () => {
          await logout();
          navigation.reset({ index: 0, routes: [{ name: 'Login' }] });
        },
      },
    ]);
  };

  const themeOptions: { label: string; value: ThemePref }[] = [
    { label: '跟随系统', value: 'system' },
    { label: '深色', value: 'dark' },
    { label: '浅色', value: 'light' },
  ];

  return (
    <SafeAreaView edges={['bottom']} style={{ flex: 1, backgroundColor: colors.bg }}>
      <ScrollView contentContainerStyle={styles.container}>

        <SectionHeader label="SERVER" colors={colors} />
        {editingUrl ? (
          <View style={[styles.urlEditRow, { backgroundColor: colors.bg3, borderColor: colors.border }]}>
            <TextInput
              style={[styles.urlInput, { color: colors.text }]}
              value={urlInput}
              onChangeText={setUrlInput}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
              autoFocus
            />
            <Pressable onPress={handleSaveUrl} style={[styles.saveBtn, { backgroundColor: colors.accent }]}>
              <Text style={{ color: '#fff', fontSize: 13, fontWeight: '600' }}>保存</Text>
            </Pressable>
            <Pressable onPress={() => setEditingUrl(false)}>
              <Text style={{ color: colors.text3, fontSize: 13, marginLeft: 8 }}>取消</Text>
            </Pressable>
          </View>
        ) : (
          <SettingsRow
            label="服务器地址"
            value={serverUrl || '未配置'}
            onPress={() => { setUrlInput(serverUrl); setEditingUrl(true); }}
            colors={colors}
          />
        )}

        <SectionHeader label="APPEARANCE" colors={colors} />
        <View style={[styles.row, { backgroundColor: colors.bg3, borderColor: colors.border }]}>
          <Text style={[styles.rowLabel, { color: colors.text }]}>主题</Text>
          <View style={styles.themeOptions}>
            {themeOptions.map((opt) => (
              <Pressable
                key={opt.value}
                onPress={() => setTheme(opt.value)}
                style={[
                  styles.themeOpt,
                  {
                    backgroundColor: themePref === opt.value ? colors.accent : colors.bgInput,
                    borderColor: themePref === opt.value ? colors.accent : colors.border,
                  },
                ]}
              >
                <Text style={[styles.themeOptText, { color: themePref === opt.value ? '#fff' : colors.text2 }]}>
                  {opt.label}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>

        <SectionHeader label="ACCOUNT" colors={colors} />
        <SettingsRow label="退出登录" onPress={handleLogout} colors={{ ...colors, text: colors.red }} />

        <Text style={[styles.version, { color: colors.text3 }]}>Version 1.0.0</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16, gap: 2 },
  sectionHeader: {
    fontSize: 11,
    fontWeight: '600',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
    marginTop: 20,
    marginBottom: 6,
    paddingHorizontal: 4,
  },
  row: {
    borderRadius: 10,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 14,
    paddingVertical: 12,
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 52,
  },
  rowLabel: { fontSize: 15, fontWeight: '500' },
  rowValue: { fontSize: 12, marginTop: 2 },
  chevron: { fontSize: 20 },
  urlEditRow: {
    borderRadius: 10,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 14,
    paddingVertical: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  urlInput: { flex: 1, fontSize: 13 },
  saveBtn: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
  },
  themeOptions: { flexDirection: 'row', gap: 6, marginLeft: 'auto' },
  themeOpt: {
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 8,
    borderWidth: 1,
  },
  themeOptText: { fontSize: 12, fontWeight: '500' },
  version: { fontSize: 12, textAlign: 'center', marginTop: 32 },
});
