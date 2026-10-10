package io.visualised.app;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.Collections;

/**
 * Hands one app to phones nearby: a very small web server that gives out that app's page and nothing else, for
 * as long as the owner keeps the share box open. It answers only on the local network, never the internet.
 */
final class Sharer {
    private final ServerSocket socket;
    private final byte[] page;
    private final File installer;           // Visualised itself, for a phone that hasn't got it
    private volatile boolean open = true;

    // Added to the page as it is handed over: opened in a browser it then offers to open in the Visualised app
    // (as a page previewed from the designer does), and "Get the app" fetches the app from this phone, so the
    // whole handover needs no internet.
    private static final String OFFER = "<script>window.VML_PREVIEW = true;"
            + "(function(){var n=0,t=setInterval(function(){var b=document.getElementById('vml_offer');"
            + "if(!b){if(++n>40)clearInterval(t);return}clearInterval(t);var g=null,a=b.querySelectorAll('a');"
            + "for(var i=0;i<a.length;i++)if(/Get the app/.test(a[i].textContent))g=a[i];"
            + "if(!g){g=document.createElement('a');g.textContent='Get the app';"
            + "g.style.cssText='color:#93C5FD;text-decoration:none;white-space:nowrap';b.insertBefore(g,b.lastChild)}"
            + "g.href='/Visualised.apk'},300)})();</script>\n";

    Sharer(File file, File installer) throws IOException {
        this.installer = installer;
        String html;
        try (FileInputStream in = new FileInputStream(file)) {
            html = new String(Apps.readAll(in, 64 * 1024 * 1024), StandardCharsets.UTF_8);
        }
        // So the page, opened in a browser, offers to open in the Visualised app (as one previewed from the designer does).
        int head = html.indexOf("</head>");
        if (head >= 0 && !html.contains("g.href='/Visualised.apk'")) {
            html = html.substring(0, head) + OFFER + html.substring(head);
        }
        page = html.getBytes(StandardCharsets.UTF_8);
        socket = new ServerSocket(0);
        Thread serving = new Thread(() -> {
            while (open) {
                try {
                    final Socket caller = socket.accept();
                    new Thread(() -> answer(caller), "visualised-share-answer").start();
                } catch (IOException closed) {
                    return;
                }
            }
        }, "visualised-share");
        serving.setDaemon(true);
        serving.start();
    }

    int port() {
        return socket.getLocalPort();
    }

    void close() {
        open = false;
        try {
            socket.close();
        } catch (IOException ignored) {
            // it is shut either way
        }
    }

    private void answer(Socket caller) {
        try (Socket c = caller) {
            c.setSoTimeout(8000);
            BufferedReader in = new BufferedReader(new InputStreamReader(c.getInputStream(), StandardCharsets.ISO_8859_1));
            String first = in.readLine();
            for (String line = first; line != null && !line.isEmpty(); ) {
                line = in.readLine();                   // the rest of what was asked isn't needed
            }
            String[] parts = first == null ? new String[0] : first.split(" ");
            String path = parts.length > 1 ? parts[1] : "";
            int query = path.indexOf('?');
            if (query >= 0) {
                path = path.substring(0, query);
            }
            OutputStream out = c.getOutputStream();
            boolean get = parts.length > 0 && ("GET".equals(parts[0]) || "HEAD".equals(parts[0]));
            if (get && (path.equals("/") || path.equals("/index.html"))) {
                out.write(("HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: " + page.length
                        + "\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n").getBytes(StandardCharsets.ISO_8859_1));
                if ("GET".equals(parts[0])) {
                    out.write(page);
                }
            } else if (get && path.equals("/Visualised.apk") && installer != null && installer.isFile()) {
                out.write(("HTTP/1.1 200 OK\r\nContent-Type: application/vnd.android.package-archive\r\nContent-Length: " + installer.length()
                        + "\r\nContent-Disposition: attachment; filename=\"Visualised.apk\"\r\nConnection: close\r\n\r\n").getBytes(StandardCharsets.ISO_8859_1));
                if ("GET".equals(parts[0])) {
                    try (FileInputStream apk = new FileInputStream(installer)) {
                        byte[] buffer = new byte[65536];
                        for (int n; (n = apk.read(buffer)) > 0; ) {
                            out.write(buffer, 0, n);
                        }
                    }
                }
            } else if (get && path.startsWith("/_")) {  // the page's notes to a designer: there is none here
                out.write("HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n".getBytes(StandardCharsets.ISO_8859_1));
            } else {
                out.write("HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".getBytes(StandardCharsets.ISO_8859_1));
            }
            out.flush();
        } catch (IOException | RuntimeException ignored) {
            // a caller that went away
        }
    }

    /**
     * This phone's address on the local network, or null if it isn't on one. Its own hotspot comes first (a friend
     * who has joined it can always reach this phone), then Wi-Fi. The mobile network is never used: a phone's
     * address there can look local, but nobody nearby can reach it.
     */
    static String address() {
        try {
            String hotspot = null, wifi = null, other = null;
            for (NetworkInterface net : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                String name = net.getName().toLowerCase();
                if (!net.isUp() || net.isLoopback() || name.startsWith("rmnet") || name.startsWith("ccmni") || name.startsWith("pdp")
                        || name.startsWith("v4-") || name.startsWith("clat") || name.startsWith("tun") || name.startsWith("dummy")) {
                    continue;
                }
                for (InetAddress a : Collections.list(net.getInetAddresses())) {
                    if (!(a instanceof Inet4Address) || !a.isSiteLocalAddress()) {
                        continue;
                    }
                    if (name.startsWith("ap") || name.startsWith("swlan") || name.startsWith("softap") || name.startsWith("wlan1") || name.startsWith("wl0.")) {
                        hotspot = a.getHostAddress();
                    } else if (name.startsWith("wlan")) {
                        wifi = a.getHostAddress();
                    } else {
                        other = a.getHostAddress();
                    }
                }
            }
            return hotspot != null ? hotspot : wifi != null ? wifi : other;
        } catch (IOException | RuntimeException e) {
            return null;
        }
    }
}
