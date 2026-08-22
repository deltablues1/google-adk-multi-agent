#!/usr/bin/env bash
# Build and sign Jarvis Launcher without Gradle or the Android Studio SDK.
#
# Everything used here is in Debian: default-jdk, aapt, dx, zipalign,
# apksigner. The one piece Debian does not ship is android.jar (the compile
# stub for the android.* classes), which is fetched once and cached.
#
#   sudo apt install -y default-jdk aapt dx zipalign apksigner
#   ./build.sh
#
# Result: build/jarvis-launcher.apk, ready to sideload.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BUILD="$HERE/build"
ANDROID_JAR="$HERE/android.jar"
KEYSTORE="$HERE/jarvis-launcher.keystore"
STOREPASS="${JARVIS_KEYSTORE_PASS:-jarvis-launcher}"

# API 30 stub. Compiling against a newer platform than the TV runs is fine;
# the app only touches APIs that have existed since API 1.
ANDROID_JAR_URL="https://raw.githubusercontent.com/Sable/android-platforms/master/android-30/android.jar"

need() { command -v "$1" >/dev/null || { echo "nedostaje: $1 (sudo apt install $2)" >&2; exit 1; }; }
need javac default-jdk
need aapt aapt
need zipalign zipalign
need apksigner apksigner
need keytool default-jdk
command -v dx >/dev/null || command -v d8 >/dev/null || {
    echo "nedostaje: dx ili d8 (sudo apt install dx)" >&2; exit 1; }

[ -f "$ANDROID_JAR" ] || {
    echo "== dohvaćam android.jar (jednokratno)"
    curl -fsSL "$ANDROID_JAR_URL" -o "$ANDROID_JAR"
}

rm -rf "$BUILD"
mkdir -p "$BUILD/classes" "$BUILD/apk"

echo "== javac"
javac -source 8 -target 8 -nowarn \
      -bootclasspath "$ANDROID_JAR" -classpath "$ANDROID_JAR" \
      -d "$BUILD/classes" \
      $(find "$HERE/src" -name '*.java')

echo "== dex"
if command -v d8 >/dev/null; then
    d8 --lib "$ANDROID_JAR" --output "$BUILD/apk" \
       $(find "$BUILD/classes" -name '*.class')
else
    dx --dex --output="$BUILD/apk/classes.dex" "$BUILD/classes"
fi

echo "== aapt: manifest + resources -> unsigned apk"
aapt package -f -M "$HERE/AndroidManifest.xml" -I "$ANDROID_JAR" \
     -F "$BUILD/unsigned.apk"
( cd "$BUILD/apk" && aapt add -f "$BUILD/unsigned.apk" classes.dex >/dev/null )

echo "== potpis"
[ -f "$KEYSTORE" ] || keytool -genkeypair -v -keystore "$KEYSTORE" \
    -alias jarvis -keyalg RSA -keysize 2048 -validity 10950 \
    -storepass "$STOREPASS" -keypass "$STOREPASS" \
    -dname "CN=Jarvis Launcher, O=Home, C=HR" >/dev/null

zipalign -f 4 "$BUILD/unsigned.apk" "$BUILD/aligned.apk"
apksigner sign --ks "$KEYSTORE" --ks-key-alias jarvis \
    --ks-pass "pass:$STOREPASS" --key-pass "pass:$STOREPASS" \
    --out "$BUILD/jarvis-launcher.apk" "$BUILD/aligned.apk"
apksigner verify "$BUILD/jarvis-launcher.apk"

rm -f "$BUILD/unsigned.apk" "$BUILD/aligned.apk"
echo
echo "gotovo: $BUILD/jarvis-launcher.apk"
ls -la "$BUILD/jarvis-launcher.apk"
