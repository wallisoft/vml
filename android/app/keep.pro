# Visualised's own classes stay whole: the page reaches them by name (window.VisualisedDevice), and an exported
# app's manifest names them. Only the libraries (ZXing, and Firebase in the push template) are trimmed.
-keep class io.visualised.app.** { *; }
-keepattributes *Annotation*,Signature,InnerClasses,EnclosingMethod
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
# names left as they are, so a crash report reads the same as the source
-dontobfuscate
