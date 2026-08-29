import { StatusBar } from 'expo-status-bar';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, BackHandler, SafeAreaView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { WebView } from 'react-native-webview';

const COACH_URL = 'https://snowschool.app/coach';

export default function App() {
  const webView = useRef<WebView>(null);
  const [canGoBack, setCanGoBack] = useState(false);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    const subscription = BackHandler.addEventListener('hardwareBackPress', () => {
      if (!canGoBack) return false;
      webView.current?.goBack();
      return true;
    });
    return () => subscription.remove();
  }, [canGoBack]);

  return (
    <SafeAreaView style={styles.app}>
      <StatusBar style="light" />
      <View style={styles.topBar}>
        <View style={styles.brandMark} />
        <View>
          <Text style={styles.kicker}>HORSESHOE VALLEY</Text>
          <Text style={styles.title}>Snow School Coach</Text>
        </View>
        {canGoBack && <TouchableOpacity style={styles.backButton} onPress={() => webView.current?.goBack()}><Text style={styles.backText}>Back</Text></TouchableOpacity>}
      </View>
      {offline && <View style={styles.offlineBanner}><Text style={styles.offlineText}>You’re offline. Reconnect to update a class.</Text><TouchableOpacity onPress={() => webView.current?.reload()}><Text style={styles.retry}>Retry</Text></TouchableOpacity></View>}
      <WebView
        ref={webView}
        source={{ uri: COACH_URL }}
        originWhitelist={['https://*']}
        sharedCookiesEnabled
        thirdPartyCookiesEnabled={false}
        allowsBackForwardNavigationGestures
        setSupportMultipleWindows={false}
        startInLoadingState
        onNavigationStateChange={(state) => setCanGoBack(state.canGoBack)}
        onLoad={() => setOffline(false)}
        onError={() => setOffline(true)}
        renderLoading={() => <View style={styles.loading}><ActivityIndicator size="large" color="#b43d29" /><Text>Opening today’s classes…</Text></View>}
        style={styles.webView}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  app: { flex: 1, backgroundColor: '#15352f' },
  topBar: { minHeight: 58, paddingHorizontal: 16, flexDirection: 'row', alignItems: 'center', gap: 11, backgroundColor: '#15352f' },
  brandMark: { width: 10, height: 30, backgroundColor: '#b43d29' },
  kicker: { color: '#9bb0aa', fontSize: 8, fontWeight: '700', letterSpacing: 1.4 },
  title: { color: '#ffffff', fontSize: 16, fontWeight: '700' },
  backButton: { marginLeft: 'auto', paddingVertical: 10, paddingLeft: 18 },
  backText: { color: '#ffffff', fontSize: 13, fontWeight: '700' },
  offlineBanner: { paddingHorizontal: 16, minHeight: 46, backgroundColor: '#f5e3e0', flexDirection: 'row', alignItems: 'center' },
  offlineText: { flex: 1, color: '#771f19', fontSize: 12 },
  retry: { color: '#771f19', fontWeight: '700', textTransform: 'uppercase' },
  webView: { flex: 1, backgroundColor: '#fbfaf6' },
  loading: { position: 'absolute', inset: 0, backgroundColor: '#fbfaf6', alignItems: 'center', justifyContent: 'center', gap: 14 },
});
