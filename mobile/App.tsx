import { StatusBar } from 'expo-status-bar';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, BackHandler, Image, Keyboard, KeyboardAvoidingView, Linking, Modal, Platform, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { WebView } from 'react-native-webview';

type School = { name: string; location: string; portalUrl: string };
type AppScreen = 'splash' | 'school' | 'portal';
type PortalTab = 'today' | 'records' | null;

const SCHOOL_DIRECTORY: Record<string, School> = {
  HORSESHOE: { name: 'Horseshoe Valley', location: 'Barrie, Ontario', portalUrl: 'https://snowschool.app/login?next=/coach' },
};
const SCHOOL_ALIASES: Record<string, string> = { HORSESHOEVALLEY: 'HORSESHOE', HSV: 'HORSESHOE' };
const APP_ORIGIN = 'https://snowschool.app';
const NATIVE_SHELL_CSS = `
  (function () {
    var style = document.getElementById('snow-school-native-shell');
    if (!style) {
      style = document.createElement('style');
      style.id = 'snow-school-native-shell';
      style.textContent = '.site-header,.utility-bar,.site-footer,.coach-bottom-nav{display:none!important}.main-content{padding-top:20px!important;padding-bottom:32px!important}body{font-family:-apple-system,BlinkMacSystemFont,sans-serif!important;background:#f4f6f4!important}h1,h2,h3{font-family:inherit!important;letter-spacing:-.03em}.card,.coach-class-card,.auth-card,.session-roster-form{border-radius:16px!important;box-shadow:none!important}.btn,input,select,textarea{border-radius:10px!important;min-height:44px}input,select,textarea{font-size:16px!important}.btn{min-height:48px}.auth-container{min-height:0!important}.auth-card{padding:24px!important}.coach-today-header h2{font-size:28px!important}';
      document.head.appendChild(style);
    }
  })(); true;
`;

function resolveSchool(value: string) {
  const normalized = value.trim().toUpperCase().replace(/[^A-Z0-9]/g, '');
  return SCHOOL_DIRECTORY[SCHOOL_ALIASES[normalized] ?? normalized];
}

function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <View style={[styles.logoMark, compact && styles.logoMarkCompact]} accessibilityElementsHidden>
      <View style={styles.logoMountainLeft} />
      <View style={styles.logoMountainRight} />
      <View style={styles.logoSnowLeft} />
      <View style={styles.logoSnowRight} />
      <View style={styles.logoGround} />
    </View>
  );
}

export default function App() {
  const webView = useRef<WebView>(null);
  const [screen, setScreen] = useState<AppScreen>('splash');
  const [schoolCode, setSchoolCode] = useState('');
  const [schoolError, setSchoolError] = useState('');
  const [school, setSchool] = useState<School | null>(null);
  const [canGoBack, setCanGoBack] = useState(false);
  const [currentUrl, setCurrentUrl] = useState('');
  const [offline, setOffline] = useState(false);
  const [loading, setLoading] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setScreen('school'), 1400);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    const subscription = BackHandler.addEventListener('hardwareBackPress', () => {
      if (screen !== 'portal') return false;
      try {
        if (['/coach', '/dashboard', '/login'].includes(new URL(currentUrl).pathname)) return false;
      } catch { return false; }
      if (canGoBack) webView.current?.goBack();
      else setScreen('school');
      return true;
    });
    return () => subscription.remove();
  }, [canGoBack, screen, currentUrl]);

  const continueToSchool = () => {
    const match = resolveSchool(schoolCode);
    if (!match) {
      setSchoolError('We couldn’t find that school. Check the code and try again.');
      return;
    }
    setSchoolError('');
    Keyboard.dismiss();
    setSchool(match);
    setCurrentUrl(match.portalUrl);
    setCanGoBack(false);
    setOffline(false);
    setScreen('portal');
  };

  const currentPath = (() => { try { return new URL(currentUrl).pathname; } catch { return '/login'; } })();
  const isLogin = currentPath === '/login';
  const isTabRoot = currentPath === '/coach' || currentPath === '/dashboard';
  const activeTab: PortalTab = currentPath === '/coach' || currentPath.startsWith('/teams/') || currentPath.startsWith('/attendance/')
    ? 'today'
    : currentPath === '/dashboard'
      ? 'records'
      : null;
  const showPortalNavigation = Boolean(currentUrl && !isLogin);
  const screenTitle = isLogin ? 'Sign in' : currentPath === '/coach' ? 'Today' : currentPath === '/dashboard' ? 'Records' : currentPath.includes('evaluat') ? 'Evaluation' : 'Class details';

  const navigatePortal = (path: string) => {
    if (currentPath === path || loading) return;
    const navigate = () => webView.current?.injectJavaScript(`window.location.replace(${JSON.stringify(`${APP_ORIGIN}${path}`)}); true;`);
    if (!isTabRoot && !isLogin) Alert.alert('Leave this screen?', 'Save any changes before switching tabs.', [{ text: 'Stay', style: 'cancel' }, { text: 'Leave', onPress: navigate }]);
    else navigate();
  };

  if (screen === 'splash') {
    return (
      <SafeAreaView style={styles.splash}>
        <StatusBar style="light" />
        <View style={styles.splashGlow} />
        <BrandMark />
        <Text style={styles.splashKicker}>SNOW SCHOOL</Text>
        <Text style={styles.splashTitle}>COACH</Text>
        <Text style={styles.splashTagline}>Your day on the hill, all in one place.</Text>
        <ActivityIndicator style={styles.splashLoader} color="#ffffff" />
      </SafeAreaView>
    );
  }

  if (screen === 'school') {
    return (
      <SafeAreaView style={styles.schoolScreen}>
        <StatusBar style="dark" />
        <KeyboardAvoidingView style={styles.schoolLayout} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ flexGrow: 1 }}>
          <View style={styles.schoolHero}>
            <View style={styles.mountainOne} />
            <View style={styles.mountainTwo} />
            <View style={styles.schoolBrand}><BrandMark compact /><View><Text style={styles.brandText}>SNOW SCHOOL</Text><Text style={styles.brandSubtext}>COACH PLATFORM</Text></View></View>
            <Text style={styles.schoolHeroTitle}>Find your{`\n`}home mountain.</Text>
          </View>
          <View style={styles.schoolCard}>
            <Text style={styles.stepLabel}>WELCOME, COACH</Text>
            <Text style={styles.schoolTitle}>Enter your school ID</Text>
            <Text style={styles.schoolCopy}>Use the code provided by your snow school to open its private coach portal.</Text>
            <Text style={styles.inputLabel}>SCHOOL ID</Text>
            <TextInput
              autoCapitalize="characters"
              autoCorrect={false}
              accessibilityLabel="School ID"
              returnKeyType="go"
              value={schoolCode}
              onChangeText={(value) => { setSchoolCode(value); if (schoolError) setSchoolError(''); }}
              onSubmitEditing={continueToSchool}
              placeholder="e.g. HORSESHOE"
              placeholderTextColor="#87938f"
              style={[styles.schoolInput, schoolError ? styles.schoolInputError : null]}
            />
            {schoolError ? <Text style={styles.errorText} accessibilityLiveRegion="polite">{schoolError}</Text> : null}
            <TouchableOpacity accessibilityRole="button" disabled={!schoolCode.trim()} onPress={continueToSchool} style={[styles.continueButton, !schoolCode.trim() ? styles.continueButtonDisabled : null]}>
              <Text style={styles.continueText}>CONTINUE</Text><Text style={styles.continueArrow}>→</Text>
            </TouchableOpacity>
            <Text style={styles.helpText}>Demo school ID: <Text style={styles.helpCode}>HORSESHOE</Text></Text>
          </View>
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.app}>
      <StatusBar style="light" />
      <View style={styles.topBar}>
        {canGoBack && !isTabRoot && !isLogin ? <TouchableOpacity accessibilityLabel="Go back" accessibilityRole="button" style={styles.headerButton} onPress={() => webView.current?.goBack()}><Text style={styles.backChevron}>‹</Text></TouchableOpacity> : <View style={styles.headerButton} />}
        <View style={styles.headerTitle}><Text style={styles.kicker}>SNOW SCHOOL · {school?.name.toUpperCase()}</Text><Text style={styles.title}>{screenTitle}</Text></View>
        <TouchableOpacity accessibilityLabel="School and app options" accessibilityRole="button" style={styles.headerButton} onPress={() => setMenuOpen(true)}><Text style={styles.schoolMenu}>•••</Text></TouchableOpacity>
      </View>
      {loading && !offline ? <View style={styles.loadingBar}><ActivityIndicator size="small" color="#15352f" /><Text style={styles.loadingText}>Loading…</Text></View> : null}
      <View style={{ flex: 1 }}>
      <WebView
        ref={webView}
        source={{ uri: school?.portalUrl ?? SCHOOL_DIRECTORY.HORSESHOE.portalUrl }}
        originWhitelist={['*']}
        sharedCookiesEnabled
        thirdPartyCookiesEnabled={false}
        allowsBackForwardNavigationGestures
        setSupportMultipleWindows={false}
        startInLoadingState
        onShouldStartLoadWithRequest={(request) => {
          if (request.url === 'about:blank') return true;
          try {
            const url = new URL(request.url);
            if (url.origin === APP_ORIGIN) return true;
            if (request.isTopFrame !== false && ['https:', 'mailto:', 'tel:'].includes(url.protocol)) Linking.openURL(request.url).catch(() => Alert.alert('Unable to open link', 'Please try again later.'));
          } catch { /* Reject malformed or unsupported destinations. */ }
          return false;
        }}
        injectedJavaScript={NATIVE_SHELL_CSS}
        injectedJavaScriptBeforeContentLoaded={NATIVE_SHELL_CSS}
        onNavigationStateChange={(state) => { setCanGoBack(state.canGoBack); setCurrentUrl(state.url); }}
        onLoadStart={() => { setLoading(true); setOffline(false); }}
        onLoadEnd={() => setLoading(false)}
        onError={() => { setOffline(true); setLoading(false); }}
        onHttpError={({ nativeEvent }) => { if (nativeEvent.url === currentUrl && nativeEvent.statusCode >= 500) { setOffline(true); setLoading(false); } }}
        renderLoading={() => <View style={styles.loading}><ActivityIndicator size="large" color="#b43d29" /><Text style={styles.loadingText}>Opening {school?.name}…</Text></View>}
        style={styles.webView}
      />
      {offline ? <View style={styles.loading} accessibilityLiveRegion="polite"><Text style={styles.schoolTitle}>Couldn’t load your portal</Text><Text style={styles.connectionCopy}>Check your connection and try again. Your saved records are still in your school portal.</Text><TouchableOpacity accessibilityRole="button" style={styles.sheetAction} onPress={() => { setOffline(false); webView.current?.reload(); }}><Text style={styles.sheetActionText}>Try again</Text></TouchableOpacity></View> : null}
      </View>
      {showPortalNavigation ? (
        <View style={styles.bottomNav} accessibilityRole="tablist">
          <TouchableOpacity accessibilityRole="tab" accessibilityState={{ selected: activeTab === 'today' }} onPress={() => navigatePortal('/coach')} style={styles.navItem}>
            <Text style={[styles.navIcon, activeTab === 'today' ? styles.navActive : null]}>●</Text>
            <Text style={[styles.navLabel, activeTab === 'today' ? styles.navActive : null]}>Today</Text>
          </TouchableOpacity>
          <TouchableOpacity accessibilityRole="tab" accessibilityState={{ selected: activeTab === 'records' }} onPress={() => navigatePortal('/dashboard')} style={styles.navItem}>
            <Text style={[styles.navIcon, activeTab === 'records' ? styles.navActive : null]}>▦</Text>
            <Text style={[styles.navLabel, activeTab === 'records' ? styles.navActive : null]}>Records</Text>
          </TouchableOpacity>
        </View>
      ) : null}
      <Modal visible={menuOpen} transparent animationType="slide" onRequestClose={() => setMenuOpen(false)}>
        <View style={styles.sheetBackdrop}>
          <TouchableOpacity style={{ flex: 1 }} accessibilityRole="button" accessibilityLabel="Close options" onPress={() => setMenuOpen(false)} />
          <SafeAreaView style={styles.sheet}>
            <View style={styles.sheetHandle} />
            <Text style={styles.schoolTitle}>{school?.name}</Text>
            <Text style={styles.connectionCopy}>{school?.location} · Snow School Coach</Text>
            <TouchableOpacity accessibilityRole="button" style={styles.sheetAction} onPress={() => { setMenuOpen(false); Alert.alert('Reload this screen?', 'Unsaved changes may be lost.', [{ text: 'Cancel', style: 'cancel' }, { text: 'Reload', onPress: () => webView.current?.reload() }]); }}><Text style={styles.sheetActionText}>Reload current screen</Text></TouchableOpacity>
            <TouchableOpacity accessibilityRole="button" style={styles.sheetAction} onPress={() => { setMenuOpen(false); Alert.alert('Change school?', 'Save any changes first. This returns to school selection; it does not sign out of your account.', [{ text: 'Stay', style: 'cancel' }, { text: 'Change school', onPress: () => { setScreen('school'); setCurrentUrl(''); setCanGoBack(false); } }]); }}><Text style={styles.sheetActionText}>Change school</Text></TouchableOpacity>
            <TouchableOpacity accessibilityRole="button" style={styles.sheetAction} onPress={() => setMenuOpen(false)}><Text style={styles.sheetActionText}>Done</Text></TouchableOpacity>
          </SafeAreaView>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  loadingBar: { minHeight: 34, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#eef2ef' },
  connectionCopy: { color: '#5d6b67', fontSize: 15, lineHeight: 22, marginVertical: 14, textAlign: 'center', paddingHorizontal: 16 },
  sheetBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,.4)' },
  sheet: { backgroundColor: '#f4f6f4', borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 24, alignItems: 'center' },
  sheetHandle: { width: 36, height: 5, backgroundColor: '#c5cdc8', borderRadius: 3, marginBottom: 12 },
  sheetAction: { minHeight: 52, borderRadius: 14, backgroundColor: '#fff', width: '90%', alignItems: 'center', justifyContent: 'center', marginBottom: 10 },
  sheetActionText: { color: '#15352f', fontSize: 16, fontWeight: '600' },
  app: { flex: 1, backgroundColor: '#142b3a' },
  splash: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#142b3a', overflow: 'hidden' },
  splashGlow: { position: 'absolute', width: 430, height: 430, borderRadius: 215, backgroundColor: '#1d3b4e', opacity: 0.62 },
  logoMark: { width: 104, height: 104, borderRadius: 7, backgroundColor: '#142b3a', overflow: 'hidden', marginBottom: 28, borderWidth: 1, borderColor: '#36576a' },
  logoMarkCompact: { width: 38, height: 38, borderRadius: 3, marginBottom: 0, borderColor: '#4b6a7b' },
  logoMountainLeft: { position: 'absolute', width: '45%', height: '45%', left: '14%', bottom: '26%', backgroundColor: '#287fa3', transform: [{ rotate: '45deg' }] },
  logoMountainRight: { position: 'absolute', width: '38%', height: '38%', right: '12%', bottom: '26%', backgroundColor: '#287fa3', transform: [{ rotate: '45deg' }] },
  logoSnowLeft: { position: 'absolute', width: '23%', height: 2, left: '22%', top: '40%', backgroundColor: '#ffffff', transform: [{ rotate: '-43deg' }] },
  logoSnowRight: { position: 'absolute', width: '19%', height: 2, right: '22%', top: '45%', backgroundColor: '#ffffff', transform: [{ rotate: '43deg' }] },
  logoGround: { position: 'absolute', left: '15%', right: '15%', height: 2, bottom: '18%', backgroundColor: '#ffffff' },
  splashKicker: { color: '#a9c6d2', fontSize: 11, fontWeight: '700', letterSpacing: 3.2, marginTop: 2 },
  splashTitle: { color: '#ffffff', fontSize: 48, fontWeight: '700', letterSpacing: 2, marginTop: 8 },
  splashTagline: { color: '#a9c6d2', fontSize: 15, marginTop: 14 },
  splashLoader: { position: 'absolute', bottom: 54 },
  schoolScreen: { flex: 1, backgroundColor: '#f6f2ea' },
  schoolLayout: { flex: 1 },
  schoolHero: { height: '39%', minHeight: 270, backgroundColor: '#142b3a', padding: 24, justifyContent: 'space-between', overflow: 'hidden' },
  schoolBrand: { flexDirection: 'row', alignItems: 'center', gap: 10, zIndex: 2 },
  brandText: { color: '#ffffff', fontSize: 11, fontWeight: '700', letterSpacing: 1.6 },
  brandSubtext: { color: '#a9c6d2', fontSize: 7, fontWeight: '600', letterSpacing: 1.3, marginTop: 3 },
  schoolHeroTitle: { color: '#ffffff', fontSize: 43, fontWeight: '300', lineHeight: 46, letterSpacing: -1.2, zIndex: 2, marginBottom: 24 },
  mountainOne: { position: 'absolute', right: -90, bottom: -110, width: 360, height: 300, backgroundColor: '#1f526b', transform: [{ rotate: '42deg' }] },
  mountainTwo: { position: 'absolute', right: 110, bottom: -180, width: 330, height: 330, backgroundColor: '#193f53', transform: [{ rotate: '42deg' }] },
  schoolCard: { flex: 1, backgroundColor: '#f6f2ea', paddingHorizontal: 26, paddingTop: 31 },
  stepLabel: { color: '#287fa3', fontSize: 10, fontWeight: '800', letterSpacing: 2 },
  schoolTitle: { color: '#142b3a', fontSize: 30, fontWeight: '600', letterSpacing: -0.6, marginTop: 9 },
  schoolCopy: { color: '#5d6b67', fontSize: 15, lineHeight: 22, marginTop: 10, marginBottom: 27 },
  inputLabel: { color: '#142b3a', fontSize: 10, fontWeight: '800', letterSpacing: 1.6, marginBottom: 8 },
  schoolInput: { height: 58, borderRadius: 8, borderWidth: 1, borderColor: '#b9c7ce', backgroundColor: '#ffffff', paddingHorizontal: 17, color: '#142b3a', fontSize: 17, fontWeight: '700', letterSpacing: 1.1 },
  schoolInputError: { borderColor: '#a92f24' },
  errorText: { color: '#a92f24', fontSize: 13, marginTop: 8 },
  continueButton: { height: 58, borderRadius: 8, backgroundColor: '#287fa3', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, marginTop: 18 },
  continueButtonDisabled: { opacity: 0.45 },
  continueText: { color: '#ffffff', fontSize: 12, fontWeight: '800', letterSpacing: 1.8 },
  continueArrow: { color: '#ffffff', fontSize: 23 },
  helpText: { color: '#73807c', fontSize: 12, textAlign: 'center', marginTop: 17 },
  helpCode: { color: '#142b3a', fontWeight: '800' },
  topBar: { minHeight: 62, paddingHorizontal: 12, flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#142b3a' },
  headerButton: { width: 42, height: 44, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { flex: 1, alignItems: 'center' },
  backChevron: { color: '#ffffff', fontSize: 34, lineHeight: 36, fontWeight: '300' },
  schoolMenu: { color: '#ffffff', fontSize: 16, fontWeight: '800', letterSpacing: 2, paddingBottom: 7 },
  kicker: { color: '#9bb0aa', fontSize: 8, fontWeight: '700', letterSpacing: 1.4 },
  title: { color: '#ffffff', fontSize: 16, fontWeight: '700' },
  offlineBanner: { paddingHorizontal: 16, minHeight: 46, backgroundColor: '#f5e3e0', flexDirection: 'row', alignItems: 'center' },
  offlineText: { flex: 1, color: '#771f19', fontSize: 12 },
  retry: { color: '#771f19', fontWeight: '700', textTransform: 'uppercase' },
  webView: { flex: 1, backgroundColor: '#fbfaf6' },
  bottomNav: { minHeight: 66, flexDirection: 'row', backgroundColor: '#ffffff', borderTopWidth: 1, borderTopColor: '#dce1de' },
  navItem: { flex: 1, minHeight: 62, alignItems: 'center', justifyContent: 'center', gap: 3 },
  navIcon: { color: '#8b9692', fontSize: 17 },
  navLabel: { color: '#6d7975', fontSize: 10, fontWeight: '800', letterSpacing: 1.1, textTransform: 'uppercase' },
  navActive: { color: '#287fa3' },
  loading: { position: 'absolute', inset: 0, backgroundColor: '#fbfaf6', alignItems: 'center', justifyContent: 'center', gap: 14 },
  loadingText: { color: '#15352f', fontSize: 14 },
});
