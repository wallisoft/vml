#!/bin/bash
# Build the Visualised phone app and put a copy where File > Export > Android app looks for it
# (vml/web/android-template.apk). Run this whenever anything under android/ changes, then commit the result.
#
#   android/make-template.sh
#
# It needs what building the app needs: the Android SDK (ANDROID_HOME, or ~/Android/Sdk) and Java 17 or later.
# The copy may be signed or not: an exported app is given its maker's signature in place of whatever is there.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
cd "$here"
./gradlew -q ${GRADLE_FLAGS:-} assembleRelease
made=$(ls -t app/build/outputs/apk/release/*.apk | head -1)
[ -f "$made" ] || { echo "no APK was built"; exit 1; }
unzip -l "$made" | grep -q "classes.dex" || { echo "$made doesn't look like an app"; exit 1; }
cp "$made" "$here/../vml/web/android-template.apk"
echo "template: vml/web/android-template.apk ($(du -h "$here/../vml/web/android-template.apk" | cut -f1), from $(basename "$made"))"
