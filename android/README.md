# Visualised for Android

Runs the apps the designer makes, on a phone, with the phone's location, camera, notifications, sharing and
vibration behind the same `Vml(...)` commands a script uses everywhere else.

~~~
./gradlew assemblePlainDebug
adb install -r app/build/outputs/apk/plain/debug/app-plain-debug.apk
~~~

For the APK people download, signed with the release key (see `app/build.gradle` for where that lives):

~~~
./gradlew assemblePlainRelease
~~~

(The APK is then `app/build/outputs/apk/plain/release/app-plain-release.apk`.)

It needs the Android SDK (platform 34) and Java 17 or later; nothing else. It is plain Java, with ZXing's core to
read QR codes.

There are two flavours from the one source. **plain** is Visualised itself and the template for exported apps.
**push** (`src/push`) adds Firebase Cloud Messaging, and is the template only for apps whose scripts use `OnPush`;
`vml/apk.py` picks it for them. `make-template.sh` builds both. Release builds are trimmed by R8 (`app/keep.pro`
keeps Visualised's own classes whole), which is what keeps the push template under 1 MB.

How it works: an app is one web page. The phone app shows it in a web view at an address that exists only
inside the app (`https://NAME.app.visualised.invalid/`) and answers every request for that address itself,
from the copy kept on the phone or by fetching from the designer's Preview on Phone. A secure address is what
lets a page use location and the camera; an address per app keeps each app's saved data apart.

- `MainActivity.java` the first screen, the web view, permissions, the camera and file chooser
- `Apps.java` the apps kept on the phone
- `Device.java` what a page can ask of the phone (`window.VisualisedDevice`)
