import React, { useState } from 'react';
import {
  View, Text, TextInput, Pressable, StyleSheet,
  KeyboardAvoidingView, ScrollView, Platform,
} from 'react-native';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/RootNavigator';
import { setServerUrl } from '../storage/settings';
import { setBaseURL } from '../api/client';
import { useTheme } from '../hooks/useTheme';

type Props = NativeStackScreenProps<RootStackParamList, 'Setup'>;

export function SetupScreen({ navigation }: Props) {
  const { colors } = useTheme();
  const [url, setUrl] = useState('http://');
  const [error, setError] = useState('');

  const handleSave = async () => {
    const trimmed = url.trim().replace(/\/$/, '');
    if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://')) {
      setError('地址必须以 http:// 或 https:// 开头');
      return;
    }
    await setServerUrl(trimmed);
    setBaseURL(trimmed);
    navigation.replace('Login');
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      style={{ flex: 1, backgroundColor: colors.bg }}
    >
      <ScrollView
        contentContainerStyle={[styles.container]}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={[styles.icon]}>📄</Text>
        <Text style={[styles.title, { color: colors.text }]}>Daily Paper</Text>
        <Text style={[styles.subtitle, { color: colors.text3 }]}>
          请输入服务器地址以开始使用
        </Text>

        <View style={styles.form}>
          <Text style={[styles.label, { color: colors.text3 }]}>服务器地址</Text>
          <TextInput
            style={[styles.input, { backgroundColor: colors.bgInput, borderColor: colors.border, color: colors.text }]}
            value={url}
            onChangeText={(v) => { setUrl(v); setError(''); }}
            placeholder="http://192.168.1.x:8000"
            placeholderTextColor={colors.text3}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            returnKeyType="done"
            onSubmitEditing={handleSave}
          />
          {error ? <Text style={[styles.error, { color: colors.red }]}>{error}</Text> : null}
        </View>

        <Pressable
          onPress={handleSave}
          style={({ pressed }) => [
            styles.button,
            { backgroundColor: colors.accent, opacity: pressed ? 0.8 : 1 },
          ]}
        >
          <Text style={styles.buttonText}>保存并继续</Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
    gap: 8,
  },
  icon: { fontSize: 48, marginBottom: 8 },
  title: { fontSize: 28, fontWeight: '700', marginBottom: 4 },
  subtitle: { fontSize: 14, textAlign: 'center', marginBottom: 24 },
  form: { width: '100%', gap: 8, marginBottom: 16 },
  label: { fontSize: 12, fontWeight: '500' },
  input: {
    height: 48,
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: 14,
    fontSize: 14,
    width: '100%',
  },
  error: { fontSize: 12, marginTop: 2 },
  button: {
    width: '100%',
    height: 52,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 8,
  },
  buttonText: { color: '#fff', fontSize: 16, fontWeight: '700' },
});
