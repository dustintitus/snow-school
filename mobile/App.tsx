import { StatusBar } from 'expo-status-bar';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, BackHandler, Image, KeyboardAvoidingView, Platform, SafeAreaView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { WebView } from 'react-native-webview';

type School = { name: string; location: string; portalUrl: string };
type AppScreen = 'splash' | 'school' | 'portal';

const SCHOOL_DIRECTORY: Record<string, School> = {
  HORSESHOE: { name: 'Horseshoe Valley', location: 'Barrie, Ontario', portalUrl: 'https://snowschool.app/login?next=/coach' },
};
const SCHOOL_ALIASES: Record<string, string> = { HORSESHOEVALLEY: 'HORSESHOE', HSV: 'HORSESHOE' };

function resolveSchool(value: string) {
  const normalized = value.trim().toUpperCase().replace(/[^A-Z0-9]/g, '');
  return SCHOOL_DIRECTORY[SCHOOL_ALIASES[normalized] ?? normalized];
}

export default function App() {
  const webView = useRef<WebView>(null);
  const [screen, setScreen] = useState<AppScreen>('splash');
  const [schoolCode, setSchoolCode] = useState('');
  const [schoolError, setSchoolError] = useState('');
  const [school, setSchool] = useState<School | null>(null);
  const [canGoBack, setCanGoBack] = useState(false);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setScreen('school'), 1400);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    const subscription = BackHandler.addEventListener('hardwareBackPress', () => {
      if (screen !== 'portal') return false;
      if (canGoBack) webView.current?.goBack();
      else setScreen('school');
      return true;
    });
    return () => subscription.remove();
  }, [canGoBack, screen]);

  const continueToSchool = () => {
    const match = resolveSchool(schoolCode);
    if (!match) {
      setSchoolError('We couldn’t find that school. Check the code and try again.');
      return;
    }
    setSchoolError('');
    setSchool(match);
    setOffline(false);
    setScreen('portal');
  };

  if (screen === 'splash') {
    return (
      <SafeAreaView style={styles.splash}>
        <StatusBar style="light" />
        <View style={styles.splashGlow} />
        <Image source={require('./assets/icon.png')} style={styles.splashLogo} accessibilityLabel="Snow School Coach" />
        <Text style={styles.splashKicker}>SNOW SCHOOL</Text>
        <Text style={styles.splashTitle}>Coach</Text>
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
          <View style={styles.schoolHero}>
            <View style={styles.mountainOne} />
            <View style={styles.mountainTwo} />
            <View style={styles.schoolBrand}><View style={styles.brandMark} /><Text style={styles.brandText}>SNOW SCHOOL COACH</Text></View>
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
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.app}>
      <StatusBar style="light" />
      <View style={styles.topBar}>
        <TouchableOpacity accessibilityLabel="Change school" accessibilityRole="button" style={styles.changeSchoolButton} onPress={() => setScreen('school')}><Text style={styles.backChevron}>‹</Text></TouchableOpacity>
        <View><Text style={styles.kicker}>{school?.location.toUpperCase()}</Text><Text style={styles.title}>{school?.name}</Text></View>
        {canGoBack ? <TouchableOpacity style={styles.webBackButton} onPress={() => webView.current?.goBack()}><Text style={styles.webBackText}>Back</Text></TouchableOpacity> : null}
      </View>
      {offline ? <View style={styles.offlineBanner}><Text style={styles.offlineText}>You’re offline. Reconnect to continue.</Text><TouchableOpacity onPress={() => webView.current?.reload()}><Text style={styles.retry}>Retry</Text></TouchableOpacity></View> : null}
      <WebView
        ref={webView}
        source={{ uri: school?.portalUrl ?? SCHOOL_DIRECTORY.HORSESHOE.portalUrl }}
        originWhitelist={['https://*']}
        sharedCookiesEnabled
        thirdPartyCookiesEnabled={false}
        allowsBackForwardNavigationGestures
        setSupportMultipleWindows={false}
        startInLoadingState
        onNavigationStateChange={(state) => setCanGoBack(state.canGoBack)}
        onLoad={() => setOffline(false)}
        onError={() => setOffline(true)}
        renderLoading={() => <View style={styles.loading}><ActivityIndicator size="large" color="#b43d29" /><Text style={styles.loadingText}>Opening {school?.name}…</Text></View>}
        style={styles.webView}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  app: { flex: 1, backgroundColor: '#15352f' },
  splash: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#15352f', overflow: 'hidden' },
  splashGlow: { position: 'absolute', width: 430, height: 430, borderRadius: 215, backgroundColor: '#224b43', opacity: 0.72 },
  splashLogo: { width: 112, height: 112, borderRadius: 24, marginBottom: 28 },
  splashKicker: { color: '#c8d5d1', fontSize: 11, fontWeight: '800', letterSpacing: 3.2 },
  splashTitle: { color: '#ffffff', fontSize: 58, fontWeight: '300', letterSpacing: -2, marginTop: 4 },
  splashTagline: { color: '#c8d5d1', fontSize: 15, marginTop: 14 },
  splashLoader: { position: 'absolute', bottom: 54 },
  schoolScreen: { flex: 1, backgroundColor: '#f6f2ea' },
  schoolLayout: { flex: 1 },
  schoolHero: { height: '39%', minHeight: 270, backgroundColor: '#15352f', padding: 24, justifyContent: 'space-between', overflow: 'hidden' },
  schoolBrand: { flexDirection: 'row', alignItems: 'center', gap: 10, zIndex: 2 },
  brandMark: { width: 9, height: 26, backgroundColor: '#b64a35' },
  brandText: { color: '#ffffff', fontSize: 11, fontWeight: '800', letterSpacing: 1.8 },
  schoolHeroTitle: { color: '#ffffff', fontSize: 43, fontWeight: '300', lineHeight: 46, letterSpacing: -1.2, zIndex: 2, marginBottom: 24 },
  mountainOne: { position: 'absolute', right: -90, bottom: -110, width: 360, height: 300, backgroundColor: '#214c43', transform: [{ rotate: '42deg' }] },
  mountainTwo: { position: 'absolute', right: 110, bottom: -180, width: 330, height: 330, backgroundColor: '#1b4038', transform: [{ rotate: '42deg' }] },
  schoolCard: { flex: 1, backgroundColor: '#f6f2ea', paddingHorizontal: 26, paddingTop: 31 },
  stepLabel: { color: '#b64a35', fontSize: 10, fontWeight: '800', letterSpacing: 2 },
  schoolTitle: { color: '#15352f', fontSize: 30, fontWeight: '600', letterSpacing: -0.6, marginTop: 9 },
  schoolCopy: { color: '#5d6b67', fontSize: 15, lineHeight: 22, marginTop: 10, marginBottom: 27 },
  inputLabel: { color: '#15352f', fontSize: 10, fontWeight: '800', letterSpacing: 1.6, marginBottom: 8 },
  schoolInput: { height: 58, borderWidth: 1, borderColor: '#b9c2be', backgroundColor: '#ffffff', paddingHorizontal: 17, color: '#15352f', fontSize: 17, fontWeight: '700', letterSpacing: 1.1 },
  schoolInputError: { borderColor: '#a92f24' },
  errorText: { color: '#a92f24', fontSize: 13, marginTop: 8 },
  continueButton: { height: 58, backgroundColor: '#b64a35', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, marginTop: 18 },
  continueButtonDisabled: { opacity: 0.45 },
  continueText: { color: '#ffffff', fontSize: 12, fontWeight: '800', letterSpacing: 1.8 },
  continueArrow: { color: '#ffffff', fontSize: 23 },
  helpText: { color: '#73807c', fontSize: 12, textAlign: 'center', marginTop: 17 },
  helpCode: { color: '#15352f', fontWeight: '800' },
  topBar: { minHeight: 62, paddingHorizontal: 12, flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#15352f' },
  changeSchoolButton: { width: 38, height: 42, alignItems: 'center', justifyContent: 'center' },
  backChevron: { color: '#ffffff', fontSize: 34, lineHeight: 36, fontWeight: '300' },
  kicker: { color: '#9bb0aa', fontSize: 8, fontWeight: '700', letterSpacing: 1.4 },
  title: { color: '#ffffff', fontSize: 16, fontWeight: '700' },
  webBackButton: { marginLeft: 'auto', paddingVertical: 10, paddingLeft: 18 },
  webBackText: { color: '#ffffff', fontSize: 13, fontWeight: '700' },
  offlineBanner: { paddingHorizontal: 16, minHeight: 46, backgroundColor: '#f5e3e0', flexDirection: 'row', alignItems: 'center' },
  offlineText: { flex: 1, color: '#771f19', fontSize: 12 },
  retry: { color: '#771f19', fontWeight: '700', textTransform: 'uppercase' },
  webView: { flex: 1, backgroundColor: '#fbfaf6' },
  loading: { position: 'absolute', inset: 0, backgroundColor: '#fbfaf6', alignItems: 'center', justifyContent: 'center', gap: 14 },
  loadingText: { color: '#15352f', fontSize: 14 },
});
