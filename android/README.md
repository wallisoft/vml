# Visualised for Android

Runs the apps the designer makes, on a phone, with the phone's location, camera, notifications, sharing and
vibration behind the same `Vml(...)` commands a script uses everywhere else.

~~~
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
~~~

For the APK people download, signed with the release key (see `app/build.gradle` for where that lives):

~~~
./gradlew assembleRelease
~~~

It needs the Android SDK (platform 34) and Java 17 or later; nothing else. It is plain Java with no libraries.

How it works: an app is one web page. The phone app shows it in a web view at an address that exists only
inside the app (`https://NAME.app.visualised.invalid/`) and answers every request for that address itself,
from the copy kept on the phone or by fetching from the designer's Preview on Phone. A secure address is what
lets a page use location and the camera; an address per app keeps each app's saved data apart.

- `MainActivity.java` the first screen, the web view, permissions, the camera and file chooser
- `Apps.java` the apps kept on the phone
- `Device.java` what a page can ask of the phone (`window.VisualisedDevice`)
