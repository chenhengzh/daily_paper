import React, { useEffect, useState } from 'react';
import { View, ActivityIndicator } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { Paper } from '../types/paper';
import { SetupScreen } from '../screens/SetupScreen';
import { LoginScreen } from '../screens/LoginScreen';
import { PaperListScreen } from '../screens/PaperListScreen';
import { PaperDetailScreen } from '../screens/PaperDetailScreen';
import { SettingsScreen } from '../screens/SettingsScreen';
import { BookmarksScreen } from '../screens/BookmarksScreen';
import { getServerUrl } from '../storage/settings';
import { setBaseURL, restoreCookieJar, client } from '../api/client';
import { useTheme } from '../hooks/useTheme';

export type RootStackParamList = {
  Setup: undefined;
  Login: undefined;
  Main: undefined;
  Detail: { paper: Paper };
  Settings: undefined;
  Bookmarks: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();

export function RootNavigator() {
  const { colors, isDark } = useTheme();
  const [initialRoute, setInitialRoute] = useState<keyof RootStackParamList | null>(null);

  useEffect(() => {
    (async () => {
      const url = await getServerUrl();
      if (!url) {
        setInitialRoute('Setup');
        return;
      }
      setBaseURL(url);
      await restoreCookieJar();
      try {
        await client.get('/papers/dates', { timeout: 8000 });
        setInitialRoute('Main');
      } catch (e: any) {
        const status = e?.response?.status;
        if (status === 401 || status === 403 || status === 302) {
          setInitialRoute('Login');
        } else {
          // Network error or server down — still try login
          setInitialRoute('Login');
        }
      }
    })();
  }, []);

  if (!initialRoute) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator color={colors.accent} size="large" />
      </View>
    );
  }

  return (
    <NavigationContainer
      theme={{
        dark: isDark,
        colors: {
          primary: colors.accent,
          background: colors.bg,
          card: colors.bg2,
          text: colors.text,
          border: colors.border,
          notification: colors.accent,
        },
        fonts: {
          regular: { fontFamily: 'System', fontWeight: '400' },
          medium: { fontFamily: 'System', fontWeight: '500' },
          bold: { fontFamily: 'System', fontWeight: '700' },
          heavy: { fontFamily: 'System', fontWeight: '800' },
        },
      }}
    >
      <Stack.Navigator
        initialRouteName={initialRoute}
        screenOptions={{
          headerStyle: { backgroundColor: colors.bg2 },
          headerTintColor: colors.text,
          headerTitleStyle: { fontWeight: '600', fontSize: 17 },
          headerShadowVisible: false,
          contentStyle: { backgroundColor: colors.bg },
        }}
      >
        <Stack.Screen name="Setup" component={SetupScreen} options={{ headerShown: false }} />
        <Stack.Screen name="Login" component={LoginScreen} options={{ headerShown: false }} />
        <Stack.Screen name="Main" component={PaperListScreen} options={{ headerShown: false }} />
        <Stack.Screen
          name="Detail"
          component={PaperDetailScreen}
          options={{ title: '论文详情', headerBackTitle: '返回' }}
        />
        <Stack.Screen
          name="Settings"
          component={SettingsScreen}
          options={{ title: '设置', headerBackTitle: '返回' }}
        />
        <Stack.Screen
          name="Bookmarks"
          component={BookmarksScreen}
          options={{ headerShown: false }}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
