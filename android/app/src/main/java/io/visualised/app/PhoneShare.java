package io.visualised.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.net.ConnectivityManager;
import android.net.LinkAddress;
import android.net.LinkProperties;
import android.net.Network;
import android.net.Uri;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;
import android.os.Build;
import android.os.Environment;
import android.os.IBinder;
import android.provider.Settings;

import org.apache.sshd.common.NamedFactory;
import org.apache.sshd.common.file.virtualfs.VirtualFileSystemFactory;
import org.apache.sshd.common.cipher.BuiltinCiphers;
import org.apache.sshd.common.kex.BuiltinDHFactories;
import org.apache.sshd.common.mac.BuiltinMacs;
import org.apache.sshd.common.signature.BuiltinSignatures;
import org.apache.sshd.server.ServerBuilder;
import org.apache.sshd.common.util.OsUtils;
import org.apache.sshd.common.util.io.PathUtils;
import org.apache.sshd.server.SshServer;
import org.apache.sshd.server.keyprovider.SimpleGeneratorHostKeyProvider;
import org.apache.sshd.sftp.server.SftpSubsystemFactory;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.File;
import java.net.Inet4Address;
import java.security.KeyPair;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

/**
 * This phone's storage as a drive on your computers (Mountie's "Share this phone"): a small SFTP server, kept
 * running by a foreground service with its notice in the phone's list while it's on. Mountie on a computer mounts it
 * as it does any SSH folder; the phone also says it's there on the Wi-Fi (as _sftp-ssh._tcp), so it can be found.
 *
 *   everything Android lets an app see: the phone's own storage (DCIM, Download, Documents...), with "All files
 *   access", which the user turns on once in Settings. The phone's apps' private folders stay private: Android
 *   gives those to no app.
 *
 * Only computers paired with the phone get in: the computer's Mountie shows a QR code holding its public key, the
 * phone scans it, and from then on that computer mounts the phone with its key (user "phone"). No passwords. The server's key is made on the phone the first time and kept, so a computer can
 * tell it's the same phone next time.
 */
public class PhoneShare extends Service {
    static final int PORT = 2222;
    static final String USER = "phone";
    private static final String CHANNEL = "phoneshare";
    private static final String PREFS = "phoneshare";

    static {
        // Android has a cut-down provider of its own called "BC". Seeing it, SSHD makes "BC" its default for everything
        // and asks it for elliptic curves it hasn't got ("no such algorithm: EC for provider BC"; or no key exchanges
        // at all). The phone's own Conscrypt has all an SSH server needs: SSHD is told to use the plain JCE, before
        // any of it loads (pairing reads a key too, not only the server).
        System.setProperty("org.apache.sshd.security.defaultProvider", "none");
        System.setProperty("org.apache.sshd.registerBouncyCastle", "false");
        System.setProperty("org.apache.sshd.security.registrars", "none");
        System.setProperty("org.apache.sshd.eccSupport", "true");
    }

    static volatile SshServer server;
    static volatile String error = "";
    static volatile SshDrives.Listener listener;
    private static NsdManager.RegistrationListener advertised;

    // ---- asked by the page (through Device)

    /** Is All files access on? Without it there's nothing much to share. */
    static boolean canSeeFiles() {
        return Environment.isExternalStorageManager();
    }

    /** Take the user to the switch for All files access, for this app. */
    static void askForFiles(Context c) {
        Intent i = new Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION, Uri.parse("package:" + c.getPackageName()));
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            c.startActivity(i);
        } catch (Exception e) {
            c.startActivity(new Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        }
    }

    static void start(Context c) {
        Intent i = new Intent(c, PhoneShare.class);
        c.startForegroundService(i);
    }

    static void stop(Context c) {
        c.stopService(new Intent(c, PhoneShare.class));
    }

    /** A new password (the old one stops working when the share next starts). */
    static String newPassword(Context c) {
        String p = makePassword();
        prefs(c).edit().putString("password", p).apply();
        if (server != null) {
            stop(c);
            start(c);
        }
        return p;
    }

    /** {on, error, files, address, addresses[], port, user, password, fingerprint, name, root} */
    static String status(Context c) {
        JSONObject o = new JSONObject();
        try {
            o.put("on", server != null && server.isStarted());
            o.put("error", error);
            o.put("files", canSeeFiles());
            List<String> ips = addresses(c);
            o.put("address", ips.isEmpty() ? "" : ips.get(0));
            o.put("addresses", new JSONArray(ips));
            o.put("port", PORT);
            o.put("user", USER);
            o.put("computers", new JSONArray(computers(c).keySet()));
            o.put("fingerprint", prefs(c).getString("fingerprint", ""));
            o.put("name", phoneName());
            o.put("root", root().getPath());
        } catch (JSONException ignored) {
        }
        return o.toString();
    }

    // ---- the service

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        showNotice();
        if (server == null) {
            new Thread(this::serve, "phoneshare").start();
        }
        return START_STICKY;
    }

    private void serve() {
        try {
            OsUtils.setAndroid(Boolean.TRUE);
            File home = getFilesDir();
            PathUtils.setUserHomeFolderResolver(home::toPath);
            System.setProperty("user.home", home.getPath());

            SshServer s = SshServer.setUpDefaultServer();
            // Only what the phone's own crypto (Conscrypt) surely has, and every ssh client (OpenSSH's sshfs, paramiko)
            // offers: SSHD's own "is it supported" checks pass curve25519 and ChaCha20 on some phones that can't do
            // them, and the connection then fails with "no such algorithm".
            s.setKeyExchangeFactories(NamedFactory.setUpTransformedFactories(false,
                    Arrays.asList(BuiltinDHFactories.ecdhp256, BuiltinDHFactories.ecdhp384, BuiltinDHFactories.ecdhp521),
                    ServerBuilder.DH2KEX));
            s.setCipherFactories(new java.util.ArrayList<>(Arrays.asList(BuiltinCiphers.aes128ctr, BuiltinCiphers.aes192ctr,
                    BuiltinCiphers.aes256ctr, BuiltinCiphers.aes128gcm, BuiltinCiphers.aes256gcm)));
            s.setMacFactories(new java.util.ArrayList<>(Arrays.asList(BuiltinMacs.hmacsha256etm, BuiltinMacs.hmacsha512etm,
                    BuiltinMacs.hmacsha256, BuiltinMacs.hmacsha512)));
            s.setSignatureFactories(new java.util.ArrayList<>(Arrays.asList(BuiltinSignatures.nistp256, BuiltinSignatures.nistp384,
                    BuiltinSignatures.nistp521, BuiltinSignatures.rsaSHA256, BuiltinSignatures.rsaSHA512)));
            s.setPort(PORT);
            SimpleGeneratorHostKeyProvider keys = new SimpleGeneratorHostKeyProvider(new File(home, "phoneshare-hostkey.ser").toPath());
            keys.setAlgorithm("EC");
            keys.setKeySize(256);
            s.setKeyPairProvider(keys);
            final Context ctx = this;
            s.setPasswordAuthenticator(null);                    // no passwords: only computers paired by QR code
            s.setKeyboardInteractiveAuthenticator(null);
            s.setPublickeyAuthenticator((user, key, session) -> USER.equals(user) && paired(ctx, key));
            s.setFileSystemFactory(new VirtualFileSystemFactory(root().toPath()));
            s.setSubsystemFactories(Collections.singletonList(new SftpSubsystemFactory()));
            s.start();
            server = s;
            error = "";
            for (KeyPair kp : keys.loadKeys(null)) {
                prefs(this).edit().putString("fingerprint", fingerprint(kp)).apply();
                break;
            }
            advertise(this);
            tell("on", status(this));
        } catch (Throwable e) {
            error = String.valueOf(e.getMessage() == null ? e : e.getMessage());
            tell("error", error);
            stopSelf();
        }
    }

    @Override
    public void onDestroy() {
        SshServer s = server;
        server = null;
        unadvertise(this);
        if (s != null) {
            try {
                s.stop(true);
            } catch (Exception ignored) {
            }
        }
        tell("off", "");
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void showNotice() {
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager != null && manager.getNotificationChannel(CHANNEL) == null) {
            manager.createNotificationChannel(new NotificationChannel(CHANNEL, "Sharing this phone", NotificationManager.IMPORTANCE_LOW));
        }
        Intent open = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
        List<String> ips = addresses(this);
        Notification note = new Notification.Builder(this, CHANNEL)
                .setSmallIcon(android.R.drawable.stat_sys_upload)
                .setContentTitle("This phone is shared")
                .setContentText((ips.isEmpty() ? "on your Wi-Fi" : ips.get(0) + ", port " + PORT) + ", to your paired computers. Tap to stop.")
                .setContentIntent(PendingIntent.getActivity(this, 3, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT))
                .setOngoing(true)
                .build();
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(9003, note, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        } else {
            startForeground(9003, note);
        }
    }

    private static void tell(String state, String detail) {
        SshDrives.Listener l = listener;
        if (l != null) {
            l.told("phoneshare", state, detail);
        }
    }

    // ---- the phone, as the computer sees it

    /** What's shared: the phone's own storage (everything a file manager sees). */
    static File root() {
        return Environment.getExternalStorageDirectory();
    }

    static String phoneName() {
        String m = Build.MODEL == null ? "" : Build.MODEL;
        String b = Build.MANUFACTURER == null ? "" : Build.MANUFACTURER;
        if (!b.isEmpty() && !m.toLowerCase().startsWith(b.toLowerCase())) {
            m = Character.toUpperCase(b.charAt(0)) + b.substring(1) + " " + m;
        }
        return m.isEmpty() ? "Android phone" : m;
    }

    /** The phone's IPv4 addresses on its networks (Wi-Fi first). */
    static List<String> addresses(Context c) {
        List<String> out = new java.util.ArrayList<>();
        ConnectivityManager cm = c.getSystemService(ConnectivityManager.class);
        if (cm == null) {
            return out;
        }
        for (Network n : cm.getAllNetworks()) {
            LinkProperties lp = cm.getLinkProperties(n);
            if (lp == null) {
                continue;
            }
            for (LinkAddress la : lp.getLinkAddresses()) {
                if (la.getAddress() instanceof Inet4Address && !la.getAddress().isLoopbackAddress()) {
                    String ip = la.getAddress().getHostAddress();
                    boolean wifi = lp.getInterfaceName() != null && lp.getInterfaceName().startsWith("wlan");
                    if (wifi) {
                        out.add(0, ip);
                    } else {
                        out.add(ip);
                    }
                }
            }
        }
        return out;
    }

    private static void advertise(Context c) {
        NsdManager nsd = c.getSystemService(NsdManager.class);
        if (nsd == null || advertised != null) {
            return;
        }
        NsdServiceInfo info = new NsdServiceInfo();
        info.setServiceName("Mountie: " + phoneName());
        info.setServiceType("_sftp-ssh._tcp.");
        info.setPort(PORT);
        info.setAttribute("user", USER);
        info.setAttribute("app", "mountie");
        advertised = new NsdManager.RegistrationListener() {
            public void onServiceRegistered(NsdServiceInfo s) { }
            public void onRegistrationFailed(NsdServiceInfo s, int code) { }
            public void onServiceUnregistered(NsdServiceInfo s) { }
            public void onUnregistrationFailed(NsdServiceInfo s, int code) { }
        };
        try {
            nsd.registerService(info, NsdManager.PROTOCOL_DNS_SD, advertised);
        } catch (Exception e) {
            advertised = null;
        }
    }

    private static void unadvertise(Context c) {
        NsdManager nsd = c.getSystemService(NsdManager.class);
        if (nsd != null && advertised != null) {
            try {
                nsd.unregisterService(advertised);
            } catch (Exception ignored) {
            }
        }
        advertised = null;
    }

    // ---- paired computers: each one's public key, from the QR code its Mountie showed

    /** {name: base64 of the key's SSH blob} */
    static java.util.Map<String, String> computers(Context c) {
        java.util.Map<String, String> out = new java.util.TreeMap<>();
        try {
            JSONObject o = new JSONObject(prefs(c).getString("computers", "{}"));
            for (java.util.Iterator<String> it = o.keys(); it.hasNext(); ) {
                String k = it.next();
                out.put(k, o.getString(k));
            }
        } catch (JSONException ignored) {
        }
        return out;
    }

    private static void keep(Context c, java.util.Map<String, String> all) {
        prefs(c).edit().putString("computers", new JSONObject(all).toString()).apply();
    }

    /** A code scanned off a computer's Mountie: "mountie:<name> <base64 key>". "" when paired, otherwise why not. */
    static String pair(Context c, String code) {
        String s = code == null ? "" : code.trim();
        if (!s.startsWith("mountie:")) {
            return "That isn't a Mountie pairing code (Mountie on the computer: Phone, Pair a phone).";
        }
        s = s.substring(8);
        int sp = s.lastIndexOf(' ');
        if (sp <= 0) {
            return "That pairing code is incomplete: try scanning it again.";
        }
        String name = s.substring(0, sp).trim(), blob = s.substring(sp + 1).trim();
        try {
            keyOf(blob);
        } catch (Exception e) {
            return "That pairing code's key couldn't be read (" + e.getMessage() + ").";
        }
        java.util.Map<String, String> all = computers(c);
        all.put(name.isEmpty() ? "A computer" : name, blob);
        keep(c, all);
        return "";
    }

    static void forget(Context c, String name) {
        java.util.Map<String, String> all = computers(c);
        all.remove(name);
        keep(c, all);
    }

    /** An ecdsa-sha2-nistp256 key's SSH blob, read with the phone's own EC (string type, string curve, string point). */
    private static java.security.PublicKey keyOf(String blob) throws Exception {
        java.nio.ByteBuffer b = java.nio.ByteBuffer.wrap(android.util.Base64.decode(blob, android.util.Base64.DEFAULT));
        String type = new String(field(b)), curve = new String(field(b));
        byte[] q = field(b);
        if (!"ecdsa-sha2-nistp256".equals(type) || !"nistp256".equals(curve) || q.length != 65 || q[0] != 4) {
            throw new IllegalArgumentException("not a P-256 key");
        }
        java.security.AlgorithmParameters ap = java.security.AlgorithmParameters.getInstance("EC");
        ap.init(new java.security.spec.ECGenParameterSpec("secp256r1"));
        java.security.spec.ECParameterSpec spec = ap.getParameterSpec(java.security.spec.ECParameterSpec.class);
        java.security.spec.ECPoint w = new java.security.spec.ECPoint(new java.math.BigInteger(1, java.util.Arrays.copyOfRange(q, 1, 33)),
                new java.math.BigInteger(1, java.util.Arrays.copyOfRange(q, 33, 65)));
        return java.security.KeyFactory.getInstance("EC").generatePublic(new java.security.spec.ECPublicKeySpec(w, spec));
    }

    private static byte[] field(java.nio.ByteBuffer b) {
        byte[] f = new byte[b.getInt()];
        b.get(f);
        return f;
    }

    /** The same key? (compared by curve point: the offered key may come from another provider than ours) */
    private static boolean same(java.security.PublicKey a, java.security.PublicKey b) {
        if (a instanceof java.security.interfaces.ECPublicKey && b instanceof java.security.interfaces.ECPublicKey) {
            return ((java.security.interfaces.ECPublicKey) a).getW().equals(((java.security.interfaces.ECPublicKey) b).getW());
        }
        return false;
    }

    private static boolean paired(Context c, java.security.PublicKey offered) {
        for (String blob : computers(c).values()) {
            try {
                if (same(keyOf(blob), offered)) {
                    return true;
                }
            } catch (Exception ignored) {
            }
        }
        return false;
    }

    // ---- the password (no longer asked for: kept so an older Mountie page still gets an answer) and the key

    private static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    static String password(Context c) {
        String p = prefs(c).getString("password", "");
        if (p.isEmpty()) {
            p = makePassword();
            prefs(c).edit().putString("password", p).apply();
        }
        return p;
    }

    /** Three short words' worth of letters and digits, easy to read off a phone: e.g. "k7mp-x2qd-9wrt". */
    private static String makePassword() {
        String chars = "abcdefghjkmnpqrstuvwxyz23456789";           // (no l/1, o/0: read off a screen)
        SecureRandom r = new SecureRandom();
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < 12; i++) {
            if (i > 0 && i % 4 == 0) {
                b.append('-');
            }
            b.append(chars.charAt(r.nextInt(chars.length())));
        }
        return b.toString();
    }

    /** SHA256:... as ssh shows a server's key. */
    private static String fingerprint(KeyPair kp) {
        try {
            return org.apache.sshd.common.config.keys.KeyUtils.getFingerPrint(kp.getPublic());
        } catch (Exception e) {
            return "";
        }
    }
}
