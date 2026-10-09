package io.visualised.app;

import android.content.Context;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * The apps kept on this phone. Each is a folder in the app's own storage holding the page the designer made
 * (index.html), the name to show (name.txt) and where it came from (source.txt), so it can be fetched again.
 */
final class Apps {
    /** One app kept on the phone. */
    static final class Kept {
        final String id, name, source, version;
        final long when;                // when this copy was fetched
        final File icon;                // its own picture, or null

        Kept(String id, String name, String source, String version, long when, File icon) {
            this.id = id;
            this.name = name;
            this.source = source;
            this.version = version;
            this.when = when;
            this.icon = icon;
        }

        @Override
        public String toString() {
            return name;
        }
    }

    private static final Pattern TITLE = Pattern.compile("<title>(.*?)</title>", Pattern.CASE_INSENSITIVE | Pattern.DOTALL);
    private static final Pattern VERSION = Pattern.compile("<meta name=\"app-version\" content=\"([^\"]*)\"");
    private static final Pattern ICON = Pattern.compile("<link rel=\"icon\" href=\"data:image/(?:png|jpeg|webp);base64,([A-Za-z0-9+/=]+)\"");
    private static final int MAX_PAGE = 64 * 1024 * 1024;

    private final File root;

    Apps(Context context) {
        root = new File(context.getFilesDir(), "apps");
    }

    List<Kept> all() {
        List<Kept> out = new ArrayList<>();
        File[] folders = root.listFiles();
        if (folders != null) {
            for (File f : folders) {
                if (new File(f, "index.html").isFile()) {
                    out.add(kept(f));
                }
            }
        }
        Collections.sort(out, (a, b) -> a.name.compareToIgnoreCase(b.name));
        return out;
    }

    private static Kept kept(File folder) {
        File icon = new File(folder, "icon.png");
        return new Kept(folder.getName(), readText(new File(folder, "name.txt"), folder.getName()),
                readText(new File(folder, "source.txt"), ""), readText(new File(folder, "version.txt"), ""),
                new File(folder, "index.html").lastModified(), icon.isFile() ? icon : null);
    }

    /** The app already kept from this address, if there is one: keeping it again replaces it. */
    Kept from(String address) {
        for (Kept k : all()) {
            if (k.source.equals(address)) {
                return k;
            }
        }
        return null;
    }

    File page(String id) {
        return new File(new File(root, safe(id)), "index.html");
    }

    /** Fetch the page at an address and keep it. Returns the app it became. Not for the main thread. */
    Kept keep(String address, String replaceId) throws IOException {
        byte[] page = fetch(address);
        String html = new String(page, StandardCharsets.UTF_8);
        if (!html.contains("vml_window")) {
            throw new IOException("That address didn't give a Visualised app.");
        }
        Matcher m = TITLE.matcher(html);
        String name = m.find() ? unescape(m.group(1).trim()) : "App";
        if (name.isEmpty()) {
            name = "App";
        }
        String id = replaceId != null ? safe(replaceId) : freshId(name);
        File folder = new File(root, id);
        if (!folder.isDirectory() && !folder.mkdirs()) {
            throw new IOException("The app couldn't be saved on this phone.");
        }
        write(new File(folder, "index.html"), page);
        write(new File(folder, "name.txt"), name.getBytes(StandardCharsets.UTF_8));
        write(new File(folder, "source.txt"), address.getBytes(StandardCharsets.UTF_8));
        Matcher v = VERSION.matcher(html);
        write(new File(folder, "version.txt"), (v.find() ? unescape(v.group(1).trim()) : "").getBytes(StandardCharsets.UTF_8));
        File icon = new File(folder, "icon.png");
        Matcher i = ICON.matcher(html);
        byte[] picture = null;
        if (i.find()) {
            try {
                picture = android.util.Base64.decode(i.group(1), android.util.Base64.DEFAULT);
            } catch (IllegalArgumentException notBase64) {
                picture = null;
            }
        }
        if (picture != null && picture.length > 0) {
            write(icon, picture);
        } else {
            //noinspection ResultOfMethodCallIgnored
            icon.delete();
        }
        return kept(folder);
    }

    void remove(String id) {
        File folder = new File(root, safe(id));
        File[] files = folder.listFiles();
        if (files != null) {
            for (File f : files) {
                //noinspection ResultOfMethodCallIgnored
                f.delete();
            }
        }
        //noinspection ResultOfMethodCallIgnored
        folder.delete();
    }

    private String freshId(String name) {
        String base = name.toLowerCase().replaceAll("[^a-z0-9]+", "-").replaceAll("^-+|-+$", "");
        if (base.isEmpty()) {
            base = "app";
        }
        if (base.length() > 40) {
            base = base.substring(0, 40);
        }
        String id = base;
        for (int n = 2; new File(root, id).exists(); n++) {
            id = base + "-" + n;
        }
        return id;
    }

    /** A name safe to use as a folder and as part of a web address: letters, digits and dashes. */
    static String safe(String id) {
        String s = id == null ? "" : id.toLowerCase().replaceAll("[^a-z0-9-]", "");
        return s.isEmpty() ? "app" : s;
    }

    static byte[] fetch(String address) throws IOException {
        HttpURLConnection c = open(address, null, 20000);
        try {
            int code = c.getResponseCode();
            if (code != 200) {
                throw new IOException("The computer answered " + code + ".");
            }
            try (InputStream in = c.getInputStream()) {
                return readAll(in, MAX_PAGE);
            }
        } finally {
            c.disconnect();
        }
    }

    /**
     * Ask for an address, going on to wherever it says the page has moved (Android won't by itself follow a move
     * from http to https, which is what most web sites answer a plain address with). The answer has arrived when
     * this returns.
     */
    static HttpURLConnection open(String address, Map<String, String> headers, int readTimeout) throws IOException {
        URL url = new URL(address);
        for (int hop = 0; ; hop++) {
            HttpURLConnection c = (HttpURLConnection) url.openConnection();
            c.setConnectTimeout(8000);
            c.setReadTimeout(readTimeout);
            c.setInstanceFollowRedirects(false);
            if (headers != null) {
                for (Map.Entry<String, String> h : headers.entrySet()) {
                    c.setRequestProperty(h.getKey(), h.getValue());
                }
            }
            int code = c.getResponseCode();
            String moved = c.getHeaderField("Location");
            if (code < 300 || code >= 400 || code == 304 || moved == null || hop >= 5) {
                return c;
            }
            c.disconnect();
            url = new URL(url, moved);
            if (!"http".equals(url.getProtocol()) && !"https".equals(url.getProtocol())) {
                throw new IOException("The page has moved somewhere this app can't follow.");
            }
        }
    }

    /** The address to fetch for what was typed or linked: https for a web site, http for a computer on the network. */
    static String address(String authority, String path) {
        String name = authority == null ? "" : authority;
        int colon = name.lastIndexOf(':');
        String host = colon > 0 && !name.endsWith("]") ? name.substring(0, colon) : name;
        boolean local = colon > 0 || host.matches("[0-9.]+") || host.equals("localhost") || !host.contains(".") || host.endsWith(".local");
        return (local ? "http://" : "https://") + name + (path == null || path.isEmpty() ? "/" : path);
    }

    static byte[] readAll(InputStream in, int limit) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[65536];
        int n;
        while ((n = in.read(buffer)) > 0) {
            out.write(buffer, 0, n);
            if (out.size() > limit) {
                throw new IOException("That page is too big.");
            }
        }
        return out.toByteArray();
    }

    private static void write(File file, byte[] data) throws IOException {
        try (FileOutputStream out = new FileOutputStream(file)) {
            out.write(data);
        }
    }

    private static String readText(File file, String otherwise) {
        try (FileInputStream in = new FileInputStream(file)) {
            String s = new String(readAll(in, 4096), StandardCharsets.UTF_8).trim();
            return s.isEmpty() ? otherwise : s;
        } catch (IOException e) {
            return otherwise;
        }
    }

    private static String unescape(String s) {
        return s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", "\"").replace("&#39;", "'").replace("&amp;", "&");
    }
}
