# How To Turn Your App into an Android App

## Introduction

Visualised can make an Android app (an APK) from a form: its own icon, its own name in the app drawer, installable on any Android phone. Phone features (camera, QR codes, vibration, notifications, sharing and more) work through `Vml()` commands, as on the desktop.

## Prerequisites

- **Visualised Pro.** Making APKs is a Pro feature (Settings > Upgrade Licence in the designer).
- A form, ideally drawn at a phone's size: **File > New Phone Form** in the designer makes one.

## Step 1: Make the APK

```
vml apk TipCalc.vml TipCalc.apk
```

It prints the app's package name, its version (the form's `Version=`) and what it asks the phone for.

## Step 2: Keep a copy of your signing key

Android only lets an update install over an app signed with the same key. Visualised makes that key the first time and keeps it for you; keep a copy somewhere safe:

```
vml apk-key save ~/visualised-android-key.backup
```

On a new computer, `vml apk-key restore ~/visualised-android-key.backup` brings it back. Lose it, and phones won't accept updates to your app: users would have to uninstall and install again.

## Step 3: Install it on a phone

Copy `TipCalc.apk` to the phone (or download it from your website) and open it. Android asks to allow installing from that source the first time.

## Step 4: Release a new version

Raise `Version=` in the form, make the APK again with the same command, and install it over the old one: the app updates and keeps its data.

## Conclusion

One command makes the app; one saved key keeps it updatable. To let users know when there's a new version, see [How To Ship Updates to Your Users](How-To-Ship-Updates-to-Your-Users).
