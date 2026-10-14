package io.visualised.app;

import android.content.Context;
import android.content.SharedPreferences;
import android.content.res.AssetFileDescriptor;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.graphics.Point;
import android.net.Uri;
import android.os.CancellationSignal;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.ParcelFileDescriptor;
import android.os.ProxyFileDescriptorCallback;
import android.os.storage.StorageManager;
import android.provider.DocumentsContract;
import android.provider.DocumentsContract.Document;
import android.provider.DocumentsContract.Root;
import android.provider.DocumentsProvider;
import android.system.ErrnoException;
import android.system.OsConstants;
import android.util.Base64;
import android.webkit.MimeTypeMap;

import com.jcraft.jsch.ChannelSftp;
import com.jcraft.jsch.HostKey;
import com.jcraft.jsch.HostKeyRepository;
import com.jcraft.jsch.JSch;
import com.jcraft.jsch.JSchException;
import com.jcraft.jsch.Session;
import com.jcraft.jsch.SftpATTRS;
import com.jcraft.jsch.SftpException;
import com.jcraft.jsch.UIKeyboardInteractive;
import com.jcraft.jsch.UserInfo;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Vector;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Folders on SSH servers in the phone's Files app (and in every app's "open file"), as Google Drive's are: an app's
 * Vml("SshMount", drive) adds one, Vml("SshUnmount", name) takes it away. Each drive is a root here, read and
 * written over SFTP. The drives are kept in this app's own settings, so they are still there in Files when the app
 * isn't running; nothing else on the phone can read them.
 *
 *   document ids are  <drive name>:<path inside the drive>   (the drive's own folder is "<name>:/")
 *
 * The server's key is remembered the first time it is met and a different one is refused afterwards, as ssh does;
 * the app hears of it through Listener.told("sshdrive", name, "hostkey|" + fingerprint).
 */
public final class SshDrives extends DocumentsProvider {
    static String AUTHORITY = "io.visualised.app.sshdrives";   // (an app exported on its own has its own: set as it starts)
    private static final String PREFS = "sshdrives";

    /** What the app on screen hears: tell("sshdrive", name, state + "|" + detail). */
    interface Listener {
        void told(String what, String a, String b);
    }

    static volatile Listener listener;
    private static final Map<String, Conn> conns = new ConcurrentHashMap<>();
    private static final Map<String, String[]> status = new ConcurrentHashMap<>();
    private static HandlerThread worker;
    private static Handler work;

    static {
        // A phone's Java has no Ed25519 or X25519 of its own: Bouncy Castle's are used, so ed25519 keys and servers work.
        JSch.setConfig("ssh-ed25519", "com.jcraft.jsch.bc.SignatureEd25519");
        JSch.setConfig("ssh-ed448", "com.jcraft.jsch.bc.SignatureEd448");
        JSch.setConfig("keypairgen.eddsa", "com.jcraft.jsch.bc.KeyPairGenEdDSA");
        JSch.setConfig("xdh", "com.jcraft.jsch.bc.XDH");
        JSch.setConfig("server_host_key", "ssh-ed25519,ecdsa-sha2-nistp256,ecdsa-sha2-nistp384,ecdsa-sha2-nistp521,rsa-sha2-512,rsa-sha2-256");
        JSch.setConfig("PubkeyAcceptedAlgorithms", "ssh-ed25519,ecdsa-sha2-nistp256,ecdsa-sha2-nistp384,ecdsa-sha2-nistp521,rsa-sha2-512,rsa-sha2-256,ssh-rsa");
    }

    static synchronized Handler work() {
        if (work == null) {
            worker = new HandlerThread("sshdrives");
            worker.start();
            work = new Handler(worker.getLooper());
        }
        return work;
    }

    // ── the drives, kept in this app's settings ──

    private static SharedPreferences prefs(Context c) {
        return c.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    static synchronized JSONObject drives(Context c) {
        try {
            return new JSONObject(prefs(c).getString("drives", "{}"));
        } catch (JSONException e) {
            return new JSONObject();
        }
    }

    private static synchronized void keep(Context c, JSONObject all) {
        prefs(c).edit().putString("drives", all.toString()).apply();
    }

    static synchronized JSONObject drive(Context c, String name) {
        return drives(c).optJSONObject(name);
    }

    private static void say(String name, String state, String detail) {
        status.put(name, new String[]{state, detail == null ? "" : detail});
        Listener l = listener;
        if (l != null) {
            l.told("sshdrive", name, state + "|" + (detail == null ? "" : detail));
        }
    }

    private static void rootsChanged(Context c) {
        c.getContentResolver().notifyChange(DocumentsContract.buildRootsUri(AUTHORITY), null);
    }

    /** Add (or change) a drive and check it can be reached; the app hears connecting, then mounted, offline or error. */
    static void mount(Context context, String json) {
        final Context c = context.getApplicationContext();
        JSONObject d;
        try {
            d = new JSONObject(json);
        } catch (JSONException e) {
            return;
        }
        final String name = d.optString("name", d.optString("host")).replace(":", "-").replace("/", "-").trim();
        if (name.isEmpty() || d.optString("host").isEmpty()) {
            say(name, "error", "A drive needs a server.");
            return;
        }
        synchronized (SshDrives.class) {
            JSONObject all = drives(c);
            JSONObject old = all.optJSONObject(name);
            try {
                d.put("name", name);
                if (d.optString("hostkey").isEmpty() && old != null && old.optString("host").equals(d.optString("host"))
                        && old.optInt("port", 22) == d.optInt("port", 22)) {
                    d.put("hostkey", old.optString("hostkey"));     // the same server: its key is already known here
                }
                all.put(name, d);
            } catch (JSONException ignored) {
            }
            keep(c, all);
        }
        Conn was = conns.remove(name);
        if (was != null) {
            was.close();
        }
        say(name, "connecting", "");
        work().post(() -> check(c, name));
    }

    private static void check(Context c, String name) {
        JSONObject d = drive(c, name);
        if (d == null) {
            return;                                     // taken away meanwhile
        }
        try {
            conn(c, name).base();
            say(name, "mounted", "in the Files app (sftp)");
            rootsChanged(c);
        } catch (Problem p) {
            if (p.offline) {
                say(name, "offline", p.getMessage());
                rootsChanged(c);                        // there in Files all the same: it tries again when opened
                work().postDelayed(() -> {
                    String[] s = status.get(name);
                    if (s != null && "offline".equals(s[0])) {
                        check(c, name);
                    }
                }, 20000);
            } else {
                say(name, "error", p.getMessage());
            }
        }
    }

    /**
     * Try a drive without adding it. The app hears tell("sshtest", name, "ok|" + server key + "|" + what it reached)
     * or ("sshtest", name, "error|" + why). Nothing is kept: the key is pinned when the drive is mounted.
     */
    static void test(Context context, String json) {
        final Context c = context.getApplicationContext();
        work().post(() -> {
            String name = "";
            Conn k = null;
            try {
                JSONObject d = new JSONObject(json);
                name = d.optString("name", d.optString("host"));
                if (d.optString("host").isEmpty()) {
                    throw new Problem("Which server? (Server is empty)", false, OsConstants.EINVAL);
                }
                k = new Conn(c, d);
                k.trial = true;
                String base = k.base();
                int things = k.run(s -> {
                    int n = 0;
                    for (Object e : s.ls(base)) {
                        String f = ((ChannelSftp.LsEntry) e).getFilename();
                        if (!f.equals(".") && !f.equals("..")) {
                            n++;
                        }
                    }
                    return n;
                });
                String user = d.optString("user");
                tellTest(name, "ok|" + k.seenKey + "|Connected to " + (user.isEmpty() ? "" : user + "@") + d.optString("host")
                        + ":" + base + (things <= 0 ? " (empty)" : " (" + things + (things == 1 ? " thing" : " things") + " there)"));
            } catch (Problem p) {
                tellTest(name, "error|" + p.getMessage());
            } catch (JSONException e) {
                tellTest(name, "error|That drive isn't JSON.");
            } finally {
                if (k != null) {
                    k.close();
                }
            }
        });
    }

    private static void tellTest(String name, String b) {
        Listener l = listener;
        if (l != null) {
            l.told("sshtest", name, b);
        }
    }

    /** Take a drive away ("" for all of them). */
    static void unmount(Context context, String name) {
        Context c = context.getApplicationContext();
        List<String> names = new ArrayList<>();
        synchronized (SshDrives.class) {
            JSONObject all = drives(c);
            if (name == null || name.isEmpty()) {
                for (Iterator<String> it = all.keys(); it.hasNext(); ) {
                    names.add(it.next());
                }
                all = new JSONObject();
            } else {
                names.add(name);
                all.remove(name);
            }
            keep(c, all);
        }
        for (String n : names) {
            Conn was = conns.remove(n);
            if (was != null) {
                work().post(was::close);
            }
            status.remove(n);
            say(n, "off", "");
        }
        rootsChanged(c);
    }

    static String status(Context c, String name) {
        try {
            if (name != null && !name.isEmpty()) {
                String[] s = status.get(name);
                if (s == null) {
                    s = new String[]{drive(c, name) != null ? "mounted" : "off", ""};
                }
                return new JSONObject().put("state", s[0]).put("detail", s[1]).toString();
            }
            JSONObject all = new JSONObject();
            for (Iterator<String> it = drives(c).keys(); it.hasNext(); ) {
                String n = it.next();
                String[] s = status.get(n);
                all.put(n, new JSONObject().put("state", s == null ? "mounted" : s[0]).put("detail", s == null ? "" : s[1]));
            }
            return all.toString();
        } catch (JSONException e) {
            return "{}";
        }
    }

    // ── one connection per drive ──

    /** Something went wrong: offline (it may come back by itself), or not (the user must change something). */
    static final class Problem extends Exception {
        final boolean offline;
        final int errno;

        Problem(String why, boolean offline, int errno) {
            super(why);
            this.offline = offline;
            this.errno = errno;
        }
    }

    private static Conn conn(Context c, String name) throws Problem {
        Conn k = conns.get(name);
        if (k == null) {
            JSONObject d = drive(c, name);
            if (d == null) {
                throw new Problem("There's no drive called " + name + " now.", false, OsConstants.ENOENT);
            }
            k = new Conn(c, d);
            Conn was = conns.putIfAbsent(name, k);
            if (was != null) {
                k = was;
            }
        }
        return k;
    }

    interface Job<T> {
        T run(ChannelSftp sftp) throws SftpException, IOException, Problem;
    }

    static final class Conn {
        final Context context;
        final JSONObject d;
        final String name;
        private Session session;
        private ChannelSftp sftp;
        private String base;
        private boolean keyChanged;
        boolean trial;                  // only being tried (SshTest): the server's key is noted, not kept
        String seenKey = "";

        Conn(Context context, JSONObject d) {
            this.context = context;
            this.d = d;
            this.name = d.optString("name");
        }

        boolean readonly() {
            return d.optBoolean("readonly", false);
        }

        synchronized void close() {
            if (sftp != null) {
                sftp.disconnect();
            }
            if (session != null) {
                session.disconnect();
            }
            sftp = null;
            session = null;
        }

        private synchronized Session session() throws Problem {
            if (session != null && session.isConnected()) {
                return session;
            }
            close();
            String auth = d.optString("auth", "password");
            JSch jsch = new JSch();
            keyChanged = false;
            jsch.setHostKeyRepository(new Pinned());
            try {
                if ("key".equals(auth)) {
                    byte[] key = keyText();
                    String pass = d.optString("passphrase");
                    jsch.addIdentity(name, key, null, pass.isEmpty() ? null : pass.getBytes(StandardCharsets.UTF_8));
                } else if ("agent".equals(auth)) {
                    throw new Problem("A phone has no SSH agent: sign in with a password, or paste the key itself.", false, OsConstants.EACCES);
                }
                String user = d.optString("user");
                Session s = jsch.getSession(user.isEmpty() ? "root" : user, d.optString("host"), d.optInt("port", 22));
                final String password = d.optString("password");
                if ("password".equals(auth)) {
                    s.setPassword(password);
                }
                s.setUserInfo(new Asker(password));
                s.setConfig("StrictHostKeyChecking", "yes");    // (Pinned says yes to a server met for the first time)
                s.setConfig("PreferredAuthentications", "publickey,keyboard-interactive,password");
                s.setServerAliveInterval(15000);
                s.setServerAliveCountMax(3);
                s.setTimeout(30000);
                s.connect(15000);
                session = s;
                return s;
            } catch (JSchException e) {
                throw problem(e);
            }
        }

        private byte[] keyText() throws Problem {
            String text = d.optString("keytext");
            if (text.isEmpty()) {
                String path = d.optString("key");
                File f = new File(path.startsWith("~/") ? "/sdcard/" + path.substring(2) : path);
                try (InputStream in = new FileInputStream(f)) {
                    byte[] all = new byte[(int) Math.min(f.length(), 65536)];
                    int n = 0, got;
                    while (n < all.length && (got = in.read(all, n, all.length - n)) > 0) {
                        n += got;
                    }
                    return all;
                } catch (IOException e) {
                    throw new Problem("On a phone, paste the key itself (the text of the key file, BEGIN to END).", false, OsConstants.EACCES);
                }
            }
            return reshape(text).getBytes(StandardCharsets.UTF_8);
        }

        private Problem problem(JSchException e) {
            String m = String.valueOf(e.getMessage());
            if (keyChanged || m.contains("HostKey has been changed") || m.contains("reject HostKey")) {
                return new Problem("This server's key isn't the one it had before. If the server was rebuilt, remove the drive "
                        + "and add it again; otherwise someone may be in the way.", false, OsConstants.EACCES);
            }
            if (m.contains("Auth fail") || m.contains("Auth cancel") || m.contains("USERAUTH fail")) {
                return new Problem("The server didn't accept that user and " + ("key".equals(d.optString("auth")) ? "key." : "password."), false, OsConstants.EACCES);
            }
            if (m.contains("invalid privatekey") || m.contains("Passphrase")) {
                return new Problem("That key couldn't be read (or its passphrase is wrong).", false, OsConstants.EACCES);
            }
            if (m.contains("UnknownHost")) {
                return new Problem("There's no server called " + d.optString("host") + " (or no internet).", true, OsConstants.EHOSTUNREACH);
            }
            if (m.contains("Connection refused")) {
                return new Problem("Couldn't reach " + d.optString("host") + ": nothing answered on port " + d.optInt("port", 22) + ".", true, OsConstants.EHOSTUNREACH);
            }
            if (m.contains("timeout") || m.contains("timed out")) {
                return new Problem("Couldn't reach " + d.optString("host") + ": no answer (a firewall, or the wrong address?).", true, OsConstants.EHOSTUNREACH);
            }
            return new Problem(m.replaceFirst("^java\\.[\\w.]+: ", ""), true, OsConstants.EHOSTUNREACH);
        }

        /** The SFTP channel for looking and changing (one at a time); files being read or written have their own. */
        private ChannelSftp sftp() throws Problem {
            if (sftp != null && sftp.isConnected()) {
                return sftp;
            }
            Session s = session();
            try {
                ChannelSftp c = (ChannelSftp) s.openChannel("sftp");
                c.connect(15000);
                sftp = c;
                if (base == null) {
                    String r = d.optString("remote").trim();
                    base = c.realpath(r.isEmpty() ? "." : r);
                    if (!c.stat(base).isDir()) {
                        throw new Problem(r + " isn't a folder on " + d.optString("host") + ".", false, OsConstants.ENOTDIR);
                    }
                }
                return c;
            } catch (SftpException e) {
                throw new Problem("There's no folder " + d.optString("remote") + " on " + d.optString("host") + ".", false, OsConstants.ENOENT);
            } catch (JSchException e) {
                throw problem(e);
            }
        }

        /** A channel of its own, for one file being read or written. */
        ChannelSftp channel() throws Problem {
            base();
            try {
                ChannelSftp c = (ChannelSftp) session().openChannel("sftp");
                c.connect(15000);
                return c;
            } catch (JSchException e) {
                throw problem(e);
            }
        }

        synchronized String base() throws Problem {
            sftp();
            return base;
        }

        String path(String inside) throws Problem {
            String b = base();
            StringBuilder p = new StringBuilder(b.equals("/") ? "" : b);
            for (String part : inside.split("/")) {
                if (!part.isEmpty() && !part.equals(".") && !part.equals("..")) {
                    p.append('/').append(part);
                }
            }
            return p.length() == 0 ? "/" : p.toString();
        }

        /** Do something over the channel, once more on a fresh connection if the line had dropped. */
        synchronized <T> T run(Job<T> job) throws Problem {
            for (int attempt = 0; ; attempt++) {
                try {
                    return job.run(sftp());
                } catch (SftpException e) {
                    boolean lost = e.id == ChannelSftp.SSH_FX_CONNECTION_LOST || e.id == ChannelSftp.SSH_FX_NO_CONNECTION
                            || (e.id == ChannelSftp.SSH_FX_FAILURE && e.getCause() instanceof IOException);
                    if (!lost) {
                        throw new Problem(e.getMessage(), false, errno(e));
                    }
                    if (attempt > 0) {
                        throw new Problem("The connection to " + d.optString("host") + " dropped.", true, OsConstants.EIO);
                    }
                } catch (IOException e) {
                    if (attempt > 0) {
                        throw new Problem(String.valueOf(e.getMessage()), true, OsConstants.EIO);
                    }
                }
                close();
            }
        }

        /** The server's key: yes the first time (remembered, and the app told), and only that one afterwards. */
        private final class Pinned implements HostKeyRepository {
            @Override
            public int check(String host, byte[] key) {
                String fp = fingerprint(key);
                String known = d.optString("hostkey");
                seenKey = fp;
                if (trial) {
                    if (known.isEmpty() || known.equals(fp)) {
                        return OK;
                    }
                    keyChanged = true;
                    return CHANGED;
                }
                if (known.isEmpty()) {
                    synchronized (SshDrives.class) {
                        JSONObject all = drives(context);
                        JSONObject mine = all.optJSONObject(name);
                        try {
                            d.put("hostkey", fp);
                            if (mine != null) {
                                mine.put("hostkey", fp);
                                keep(context, all);
                            }
                        } catch (JSONException ignored) {
                        }
                    }
                    Listener l = listener;
                    if (l != null) {
                        l.told("sshdrive", name, "hostkey|" + fp);
                    }
                    return OK;
                }
                if (known.equals(fp)) {
                    return OK;
                }
                keyChanged = true;
                return CHANGED;
            }

            @Override public void add(HostKey hostkey, UserInfo ui) { }
            @Override public void remove(String host, String type) { }
            @Override public void remove(String host, String type, byte[] key) { }
            @Override public String getKnownHostsRepositoryID() { return "visualised"; }
            @Override public HostKey[] getHostKey() { return new HostKey[0]; }
            @Override public HostKey[] getHostKey(String host, String type) { return new HostKey[0]; }
        }
    }

    /** A key pasted into a one-line box loses its line breaks: put them back (BEGIN line, body in 70s, END line). */
    static String reshape(String text) {
        java.util.regex.Matcher m = java.util.regex.Pattern.compile("(-----BEGIN [A-Z0-9 ]+-----)(.*?)(-----END [A-Z0-9 ]+-----)",
                java.util.regex.Pattern.DOTALL).matcher(text.trim());
        if (!m.find() || m.group(2).contains(":")) {
            return text;                        // (an old PEM key with headers inside is left as it is)
        }
        String body = m.group(2).replaceAll("\\s+", "");
        StringBuilder out = new StringBuilder(m.group(1)).append('\n');
        for (int i = 0; i < body.length(); i += 70) {
            out.append(body, i, Math.min(body.length(), i + 70)).append('\n');
        }
        return out.append(m.group(3)).append('\n').toString();
    }

    /** "ssh-ed25519 SHA256:..." as ssh-keygen -l shows it (and as Visualised on a computer keeps it). */
    static String fingerprint(byte[] blob) {
        String type = "ssh";
        if (blob.length > 4) {
            int n = ((blob[0] & 0xff) << 24) | ((blob[1] & 0xff) << 16) | ((blob[2] & 0xff) << 8) | (blob[3] & 0xff);
            if (n > 0 && n < 64 && 4 + n <= blob.length) {
                type = new String(blob, 4, n, StandardCharsets.US_ASCII);
            }
        }
        try {
            byte[] h = MessageDigest.getInstance("SHA-256").digest(blob);
            return type + " SHA256:" + Base64.encodeToString(h, Base64.NO_WRAP | Base64.NO_PADDING);
        } catch (Exception e) {
            return type;
        }
    }

    /** Answers a server that asks for the password as a question (keyboard-interactive) rather than outright. */
    private static final class Asker implements UserInfo, UIKeyboardInteractive {
        private final String password;

        Asker(String password) {
            this.password = password;
        }

        @Override public String getPassphrase() { return null; }
        @Override public String getPassword() { return password; }
        @Override public boolean promptPassword(String message) { return !password.isEmpty(); }
        @Override public boolean promptPassphrase(String message) { return false; }
        @Override public boolean promptYesNo(String message) { return false; }
        @Override public void showMessage(String message) { }

        @Override
        public String[] promptKeyboardInteractive(String destination, String name, String instruction, String[] prompt, boolean[] echo) {
            if (password.isEmpty()) {
                return null;
            }
            String[] answers = new String[prompt.length];
            java.util.Arrays.fill(answers, password);
            return answers;
        }
    }

    private static int errno(SftpException e) {
        switch (e.id) {
            case ChannelSftp.SSH_FX_NO_SUCH_FILE:
                return OsConstants.ENOENT;
            case ChannelSftp.SSH_FX_PERMISSION_DENIED:
                return OsConstants.EACCES;
            default:
                return OsConstants.EIO;
        }
    }

    // ── what the Files app asks ──

    private static final String[] ROOT_COLUMNS = {Root.COLUMN_ROOT_ID, Root.COLUMN_DOCUMENT_ID, Root.COLUMN_TITLE,
            Root.COLUMN_SUMMARY, Root.COLUMN_FLAGS, Root.COLUMN_ICON};
    private static final String[] DOC_COLUMNS = {Document.COLUMN_DOCUMENT_ID, Document.COLUMN_DISPLAY_NAME,
            Document.COLUMN_MIME_TYPE, Document.COLUMN_SIZE, Document.COLUMN_LAST_MODIFIED, Document.COLUMN_FLAGS};

    @Override
    public boolean onCreate() {
        AUTHORITY = getContext().getPackageName() + ".sshdrives";
        return true;
    }

    @Override
    public Cursor queryRoots(String[] projection) {
        MatrixCursor c = new MatrixCursor(projection != null ? projection : ROOT_COLUMNS);
        JSONObject all = drives(getContext());
        for (Iterator<String> it = all.keys(); it.hasNext(); ) {
            String name = it.next();
            JSONObject d = all.optJSONObject(name);
            if (d == null) {
                continue;
            }
            String user = d.optString("user");
            String remote = d.optString("remote");
            int flags = Root.FLAG_SUPPORTS_IS_CHILD | (d.optBoolean("readonly") ? 0 : Root.FLAG_SUPPORTS_CREATE);
            c.newRow().add(Root.COLUMN_ROOT_ID, name)
                    .add(Root.COLUMN_DOCUMENT_ID, name + ":/")
                    .add(Root.COLUMN_TITLE, name)
                    .add(Root.COLUMN_SUMMARY, (user.isEmpty() ? "" : user + "@") + d.optString("host") + (remote.isEmpty() ? "" : ":" + remote))
                    .add(Root.COLUMN_FLAGS, flags)
                    .add(Root.COLUMN_ICON, getContext().getApplicationInfo().icon);
        }
        c.setNotificationUri(getContext().getContentResolver(), DocumentsContract.buildRootsUri(AUTHORITY));
        return c;
    }

    private static String driveOf(String id) {
        int i = id.indexOf(':');
        return i < 0 ? id : id.substring(0, i);
    }

    private static String insideOf(String id) {
        int i = id.indexOf(':');
        String p = i < 0 ? "/" : id.substring(i + 1);
        return p.isEmpty() ? "/" : p;
    }

    private static String child(String parentId, String name) {
        return parentId.endsWith("/") ? parentId + name : parentId + "/" + name;
    }

    private static String parentOf(String id) {
        String inside = insideOf(id);
        int i = inside.lastIndexOf('/');
        return driveOf(id) + ":" + (i <= 0 ? "/" : inside.substring(0, i));
    }

    private static String nameOf(String id) {
        String inside = insideOf(id);
        return inside.substring(inside.lastIndexOf('/') + 1);
    }

    private Conn connFor(String id) throws FileNotFoundException {
        try {
            return conn(getContext(), driveOf(id));
        } catch (Problem p) {
            throw new FileNotFoundException(p.getMessage());
        }
    }

    private static FileNotFoundException notFound(Problem p) {
        return new FileNotFoundException(p.getMessage());
    }

    private static String mime(String name, boolean dir) {
        if (dir) {
            return Document.MIME_TYPE_DIR;
        }
        int dot = name.lastIndexOf('.');
        String type = dot < 0 ? null : MimeTypeMap.getSingleton().getMimeTypeFromExtension(name.substring(dot + 1).toLowerCase());
        return type != null ? type : "application/octet-stream";
    }

    private static void row(MatrixCursor c, String id, String name, SftpATTRS a, boolean readonly, boolean isRoot) {
        boolean dir = a.isDir();
        int flags = 0;
        if (!readonly) {
            flags |= dir ? Document.FLAG_DIR_SUPPORTS_CREATE : Document.FLAG_SUPPORTS_WRITE;
            if (!isRoot) {
                flags |= Document.FLAG_SUPPORTS_DELETE | Document.FLAG_SUPPORTS_RENAME;
            }
        }
        c.newRow().add(Document.COLUMN_DOCUMENT_ID, id)
                .add(Document.COLUMN_DISPLAY_NAME, name)
                .add(Document.COLUMN_MIME_TYPE, mime(name, dir))
                .add(Document.COLUMN_SIZE, dir ? null : a.getSize())
                .add(Document.COLUMN_LAST_MODIFIED, a.getMTime() * 1000L)
                .add(Document.COLUMN_FLAGS, flags);
    }

    @Override
    public Cursor queryDocument(String documentId, String[] projection) throws FileNotFoundException {
        MatrixCursor c = new MatrixCursor(projection != null ? projection : DOC_COLUMNS);
        Conn k = connFor(documentId);
        boolean isRoot = insideOf(documentId).equals("/");
        try {
            String p = k.path(insideOf(documentId));
            SftpATTRS a = k.run(s -> s.stat(p));
            row(c, documentId, isRoot ? k.name : nameOf(documentId), a, k.readonly(), isRoot);
        } catch (Problem p) {
            throw notFound(p);
        }
        return c;
    }

    @Override
    public Cursor queryChildDocuments(String parentId, String[] projection, String sortOrder) throws FileNotFoundException {
        MatrixCursor c = new MatrixCursor(projection != null ? projection : DOC_COLUMNS);
        Conn k = connFor(parentId);
        try {
            String p = k.path(insideOf(parentId));
            List<Object[]> rows = k.run(s -> {
                List<Object[]> out = new ArrayList<>();
                @SuppressWarnings("unchecked")
                Vector<ChannelSftp.LsEntry> list = s.ls(p);
                for (ChannelSftp.LsEntry e : list) {
                    String n = e.getFilename();
                    if (n.equals(".") || n.equals("..")) {
                        continue;
                    }
                    SftpATTRS a = e.getAttrs();
                    if (a.isLink()) {
                        try {
                            a = s.stat(p + "/" + n);       // where a link goes
                        } catch (SftpException broken) {
                            continue;
                        }
                    }
                    out.add(new Object[]{n, a});
                }
                return out;
            });
            for (Object[] r : rows) {
                row(c, child(parentId, (String) r[0]), (String) r[0], (SftpATTRS) r[1], k.readonly(), false);
            }
        } catch (Problem p) {
            throw notFound(p);
        }
        c.setNotificationUri(getContext().getContentResolver(), DocumentsContract.buildChildDocumentsUri(AUTHORITY, parentId));
        return c;
    }

    @Override
    public boolean isChildDocument(String parentId, String documentId) {
        if (!driveOf(parentId).equals(driveOf(documentId))) {
            return false;
        }
        String a = insideOf(parentId), b = insideOf(documentId);
        return a.equals("/") || b.equals(a) || b.startsWith(a.endsWith("/") ? a : a + "/");
    }

    @Override
    public String getDocumentType(String documentId) throws FileNotFoundException {
        if (insideOf(documentId).equals("/")) {
            return Document.MIME_TYPE_DIR;
        }
        try (Cursor c = queryDocument(documentId, new String[]{Document.COLUMN_MIME_TYPE})) {
            return c.moveToFirst() ? c.getString(0) : "application/octet-stream";
        }
    }

    private void changed(String folderId) {
        getContext().getContentResolver().notifyChange(DocumentsContract.buildChildDocumentsUri(AUTHORITY, folderId), null);
    }

    @Override
    public ParcelFileDescriptor openDocument(String documentId, String mode, CancellationSignal signal) throws FileNotFoundException {
        Conn k = connFor(documentId);
        final String path;
        try {
            path = k.path(insideOf(documentId));
        } catch (Problem p) {
            throw notFound(p);
        }
        boolean writing = mode.contains("w") || mode.contains("a");
        if (writing && k.readonly()) {
            throw new FileNotFoundException(k.name + " is read only.");
        }
        try {
            if (!writing) {
                long size = k.run(s -> s.stat(path)).getSize();
                StorageManager sm = getContext().getSystemService(StorageManager.class);
                return sm.openProxyFileDescriptor(ParcelFileDescriptor.MODE_READ_ONLY, new Reading(k, path, size), work());
            }
            // Written to a copy here, then sent to the server when the app writing it closes it.
            File temp = File.createTempFile("ssh", ".part", getContext().getCacheDir());
            if (!mode.contains("t") && !mode.equals("w")) {
                ChannelSftp ch = k.channel();
                try {
                    ch.get(path, temp.getPath());
                } catch (SftpException e) {
                    if (e.id != ChannelSftp.SSH_FX_NO_SUCH_FILE) {
                        throw new Problem(e.getMessage(), false, errno(e));
                    }
                } finally {
                    ch.disconnect();
                }
            }
            String folder = parentOf(documentId);
            return ParcelFileDescriptor.open(temp, ParcelFileDescriptor.parseMode(mode), work(), problem -> {
                try {
                    if (problem == null) {
                        ChannelSftp ch = k.channel();
                        try {
                            ch.put(temp.getPath(), path, ChannelSftp.OVERWRITE);
                        } finally {
                            ch.disconnect();
                        }
                        changed(folder);
                    }
                } catch (Problem | SftpException e) {
                    String[] s = {"error", "Couldn't save " + nameOf(documentId) + ": " + e.getMessage()};
                    Listener l = listener;
                    if (l != null) {
                        l.told("sshdrive", k.name, s[0] + "|" + s[1]);
                    }
                } finally {
                    //noinspection ResultOfMethodCallIgnored
                    temp.delete();
                }
            });
        } catch (Problem p) {
            throw notFound(p);
        } catch (IOException e) {
            throw new FileNotFoundException(e.getMessage());
        }
    }

    /** A file read straight from the server, from wherever the reader asks (one stream, reopened when it jumps). */
    private static final class Reading extends ProxyFileDescriptorCallback {
        private final Conn k;
        private final String path;
        private final long size;
        private ChannelSftp ch;
        private InputStream in;
        private long at = -1;

        Reading(Conn k, String path, long size) {
            this.k = k;
            this.path = path;
            this.size = size;
        }

        @Override
        public long onGetSize() {
            return size;
        }

        @Override
        public int onRead(long offset, int want, byte[] data) throws ErrnoException {
            try {
                if (in == null || offset != at) {
                    shut();
                    ch = k.channel();
                    in = ch.get(path, null, offset);
                    at = offset;
                }
                int n = 0;
                while (n < want) {
                    int got = in.read(data, n, want - n);
                    if (got < 0) {
                        break;
                    }
                    n += got;
                }
                at += n;
                return n;
            } catch (Problem p) {
                shut();
                throw new ErrnoException("read", p.errno);
            } catch (SftpException | IOException e) {
                shut();
                throw new ErrnoException("read", OsConstants.EIO);
            }
        }

        private void shut() {
            try {
                if (in != null) {
                    in.close();
                }
            } catch (IOException ignored) {
            }
            if (ch != null) {
                ch.disconnect();
            }
            in = null;
            ch = null;
        }

        @Override
        public void onRelease() {
            shut();
        }
    }

    @Override
    public AssetFileDescriptor openDocumentThumbnail(String documentId, Point sizeHint, CancellationSignal signal) throws FileNotFoundException {
        throw new FileNotFoundException("no thumbnails");     // (pictures would each be fetched whole just to show them small)
    }

    @Override
    public String createDocument(String parentId, String mimeType, String displayName) throws FileNotFoundException {
        Conn k = connFor(parentId);
        if (k.readonly()) {
            throw new FileNotFoundException(k.name + " is read only.");
        }
        boolean dir = Document.MIME_TYPE_DIR.equals(mimeType);
        String safe = displayName.replace("/", "-").trim();
        try {
            String folder = k.path(insideOf(parentId));
            String made = k.run(s -> {
                String name = safe;
                int dot = safe.lastIndexOf('.');
                String stem = dir || dot <= 0 ? safe : safe.substring(0, dot), ext = dir || dot <= 0 ? "" : safe.substring(dot);
                for (int n = 2; exists(s, folder + "/" + name); n++) {
                    name = stem + " (" + n + ")" + ext;         // as the Files app does: never over something already there
                }
                if (dir) {
                    s.mkdir(folder + "/" + name);
                } else {
                    s.put(new java.io.ByteArrayInputStream(new byte[0]), folder + "/" + name);
                }
                return name;
            });
            changed(parentId);
            return child(parentId, made);
        } catch (Problem p) {
            throw notFound(p);
        }
    }

    private static boolean exists(ChannelSftp s, String path) throws SftpException {
        try {
            s.lstat(path);
            return true;
        } catch (SftpException e) {
            if (e.id == ChannelSftp.SSH_FX_NO_SUCH_FILE) {
                return false;
            }
            throw e;
        }
    }

    @Override
    public void deleteDocument(String documentId) throws FileNotFoundException {
        Conn k = connFor(documentId);
        if (k.readonly() || insideOf(documentId).equals("/")) {
            throw new FileNotFoundException("Can't delete that.");
        }
        try {
            String path = k.path(insideOf(documentId));
            k.run(s -> {
                wipe(s, path);
                return null;
            });
            changed(parentOf(documentId));
        } catch (Problem p) {
            throw notFound(p);
        }
    }

    private static void wipe(ChannelSftp s, String path) throws SftpException {
        SftpATTRS a = s.lstat(path);
        if (a.isDir() && !a.isLink()) {
            @SuppressWarnings("unchecked")
            Vector<ChannelSftp.LsEntry> list = s.ls(path);
            for (ChannelSftp.LsEntry e : list) {
                if (!e.getFilename().equals(".") && !e.getFilename().equals("..")) {
                    wipe(s, path + "/" + e.getFilename());
                }
            }
            s.rmdir(path);
        } else {
            s.rm(path);
        }
    }

    @Override
    public String renameDocument(String documentId, String displayName) throws FileNotFoundException {
        Conn k = connFor(documentId);
        if (k.readonly() || insideOf(documentId).equals("/")) {
            throw new FileNotFoundException("Can't rename that.");
        }
        String safe = displayName.replace("/", "-").trim();
        String parent = parentOf(documentId);
        try {
            String from = k.path(insideOf(documentId));
            String to = k.path(insideOf(parent)) + "/" + safe;
            k.run(s -> {
                if (exists(s, to)) {
                    throw new SftpException(ChannelSftp.SSH_FX_FAILURE, "There's already something called " + safe + " there.");
                }
                s.rename(from, to);
                return null;
            });
            changed(parent);
            return child(parent, safe);
        } catch (Problem p) {
            throw notFound(p);
        }
    }
}
