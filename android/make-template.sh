#!/bin/bash
# Build the Visualised phone app and put copies where File > Export > Android app looks for them:
#   vml/web/android-template.apk        the plain template (Visualised itself, and every app without OnPush)
#   vml/web/android-template-push.apk   the push template (Firebase Cloud Messaging), for apps whose scripts use OnPush
# Run this whenever anything under android/ changes, then commit the results.
#
#   android/make-template.sh
#
# It needs what building the app needs: the Android SDK (ANDROID_HOME, or ~/Android/Sdk) and Java 17 or later.
# The copies may be signed or not: an exported app is given its maker's signature in place of whatever is there.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
cd "$here"
./gradlew -q ${GRADLE_FLAGS:-} assembleRelease
for kind in plain push; do
    made=$(ls -t app/build/outputs/apk/$kind/release/*.apk | head -1)
    [ -f "$made" ] || { echo "no $kind APK was built"; exit 1; }
    unzip -l "$made" | grep -q "classes.dex" || { echo "$made doesn't look like an app"; exit 1; }
    out="$here/../vml/web/android-template$([ $kind = push ] && echo -push || true).apk"
    cp "$made" "$out"
    echo "template: vml/web/$(basename "$out") ($(du -h "$out" | cut -f1), from $(basename "$made"))"
done
