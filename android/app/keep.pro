# Visualised's own classes stay whole: the page reaches them by name (window.VisualisedDevice), and an exported
# app's manifest names them. Only the libraries (ZXing, and Firebase in the push template) are trimmed.
-keep class io.visualised.app.** { *; }
-keepattributes *Annotation*,Signature,InnerClasses,EnclosingMethod
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
# names left as they are, so a crash report reads the same as the source
-dontobfuscate

# JSch finds its ciphers, key exchanges and signatures by class name, so they stay. Of its Bouncy Castle parts only
# Ed25519/Ed448, X25519 and ChaCha20 are kept (the rest, Twofish and the like, nobody uses), and Bouncy Castle is
# trimmed to what those need. (JSch can also log through libraries a phone hasn't got.)
-keep class !com.jcraft.jsch.bc.**, com.jcraft.jsch.** { *; }
-keep class com.jcraft.jsch.bc.SignatureEd25519, com.jcraft.jsch.bc.SignatureEd448, com.jcraft.jsch.bc.SignatureEdDSA,
            com.jcraft.jsch.bc.KeyPairGenEdDSA, com.jcraft.jsch.bc.XDH, com.jcraft.jsch.bc.ChaCha20Poly1305 { *; }
-dontwarn com.jcraft.jsch.**
-dontwarn org.apache.logging.log4j.**
-dontwarn org.slf4j.**
-dontwarn com.sun.jna.**
-dontwarn org.newsclub.net.unix.**
-dontwarn org.ietf.jgss.**
