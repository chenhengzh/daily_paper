import React, { useState } from 'react';
import {
  View, Text, TextInput, Pressable, StyleSheet,
  KeyboardAvoidingView, ScrollView, Platform, ActivityIndicator,
} from 'react-native';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/RootNavigator';
import { login } from '../api/auth';
import { getServerUrl } from '../storage/settings';
import { useTheme } from '../hooks/useTheme';

type Props = NativeStackScreenProps<RootStackParamList, 'Login'>;

export function LoginScreen({ navigation }: Props) {
  const { colors } = useTheme();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [serverUrl, setServerUrlDisplay] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  React.useEffect(() => {
    getServerUrl().then((url) => setServerUrlDisplay(url || ''));
  }, []);

  const handleLogin = async () => {
    if (!username.trim() || !password) {
      setError('请输入用户名和密码');
      return;
    }
    setLoading(true);
    setError('');
    try {
      await login(username.trim(), password);
      navigation.replace('Main');
    } catch (e: any) {
      const msg = e?.response?.status === 401
        ? '用户名或密码错误'
        : e?.response?.status === 403
        ? '账号已被禁用'
        : e?.message || '登录失败，请检查网络';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      style={{ flex: 1, backgroundColor: colors.bg }}
    >
      <ScrollView
        contentContainerStyle={styles.container}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={styles.icon}>📄</Text>
        <Text style={[styles.title, { color: colors.text }]}>Daily Paper</Text>
        <Text style={[styles.subtitle, { color: colors.text3 }]}>每日 arXiv 论文智能筛选</Text>

        {/* Server URL display */}
        <Pressable
          onPress={() => navigation.navigate('Settings')}
          style={[styles.serverRow, { backgroundColor: colors.bg3, borderColor: colors.border }]}
        >
          <View style={{ flex: 1 }}>
            <Text style={[styles.serverLabel, { color: colors.text3 }]}>Server</Text>
            <Text style={[styles.serverUrl, { color: colors.text2 }]} numberOfLines={1}>
              {serverUrl || '未配置'}
            </Text>
          </View>
          <Text style={[styles.chevron, { color: colors.text3 }]}>›</Text>
        </Pressable>

        <View style={styles.form}>
          <TextInput
            style={[styles.input, { backgroundColor: colors.bgInput, borderColor: colors.border, color: colors.text }]}
            value={username}
            onChangeText={(v) => { setUsername(v); setError(''); }}
            placeholder="用户名"
            placeholderTextColor={colors.text3}
            autoCapitalize="none"
            autoCorrect={false}
            returnKeyType="next"
          />
          <TextInput
            style={[styles.input, { backgroundColor: colors.bgInput, borderColor: colors.border, color: colors.text }]}
            value={password}
            onChangeText={(v) => { setPassword(v); setError(''); }}
            placeholder="密码"
            placeholderTextColor={colors.text3}
            secureTextEntry
            returnKeyType="done"
            onSubmitEditing={handleLogin}
          />
          {error ? <Text style={[styles.error, { color: colors.red }]}>{error}</Text> : null}
        </View>

        <Pressable
          onPress={handleLogin}
          disabled={loading}
          style={({ pressed }) => [
            styles.button,
            { backgroundColor: colors.accent, opacity: pressed || loading ? 0.7 : 1 },
          ]}
        >
          {loading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.buttonText}>登录</Text>
          )}
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
    gap: 12,
  },
  icon: { fontSize: 48, marginBottom: 4 },
  title: { fontSize: 28, fontWeight: '700' },
  subtitle: { fontSize: 14, marginBottom: 16 },
  serverRow: {
    width: '100%',
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 8,
  },
  serverLabel: { fontSize: 11, fontWeight: '500', marginBottom: 2 },
  serverUrl: { fontSize: 13 },
  chevron: { fontSize: 20, marginLeft: 8 },
  form: { width: '100%', gap: 10 },
  input: {
    height: 48,
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: 14,
    fontSize: 14,
  },
  error: { fontSize: 12 },
  button: {
    width: '100%',
    height: 52,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 4,
  },
  buttonText: { color: '#fff', fontSize: 16, fontWeight: '700' },
});
