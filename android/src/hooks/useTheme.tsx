import React, { createContext, useContext, useEffect, useState } from 'react';
import { useColorScheme } from 'react-native';
import { dark, light, ThemeColors } from '../theme/colors';
import { getThemePref, setThemePref, ThemePref } from '../storage/settings';

interface ThemeContextValue {
  colors: ThemeColors;
  isDark: boolean;
  themePref: ThemePref;
  setTheme: (pref: ThemePref) => Promise<void>;
}

const ThemeContext = createContext<ThemeContextValue>({
  colors: dark,
  isDark: true,
  themePref: 'system',
  setTheme: async () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const systemScheme = useColorScheme();
  const [pref, setPref] = useState<ThemePref>('system');

  useEffect(() => {
    getThemePref().then(setPref);
  }, []);

  const isDark =
    pref === 'dark' ? true : pref === 'light' ? false : systemScheme === 'dark';

  const setTheme = async (newPref: ThemePref) => {
    setPref(newPref);
    await setThemePref(newPref);
  };

  return (
    <ThemeContext.Provider
      value={{ colors: isDark ? dark : light, isDark, themePref: pref, setTheme }}
    >
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
