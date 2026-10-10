package io.visualised.app;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.ContentValues;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.pm.ShortcutInfo;
import android.content.pm.ShortcutManager;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.RectF;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.drawable.Icon;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.MediaStore;
import android.speech.RecognizerIntent;
import android.text.InputType;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.inputmethod.EditorInfo;
import android.webkit.GeolocationPermissions;
import android.webkit.JsPromptResult;
import android.webkit.JsResult;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLConnection;
import java.nio.charset.StandardCharsets;
import java.text.DateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Visualised on a phone: runs the apps the designer makes.
 *
 * An app is one web page. It is shown in a web view at an address of its own that exists only inside this app
 * (https://NAME.app.visualised.invalid/), and this class answers every request for that address itself: from the
 * copy kept on the phone, or by fetching from the designer on the user's computer. A secure address is what lets
 * the page use the phone's location and camera, and an address per app keeps each app's saved data apart.
 */
public class MainActivity extends Activity {
    private static final String SUFFIX = ".app.visualised.invalid";
    private static final int BRAND = 0xFF1E3A8A;
    private static final int PICK = 71;
    private static final int LISTEN = 72;
    private static final int SENT = 73;

    /** Told whether the user allowed something. */
    interface Answer {
        void got(boolean granted);
    }

    private final Handler main = new Handler(Looper.getMainLooper());
    private final Map<String, String> live = new ConcurrentHashMap<>();     // an address in here -> the computer it stands for
    private final Map<Integer, Answer> asked = new HashMap<>();
    private int nextAsk = 100;

    private Apps apps;
    private SharedPreferences prefs;
    private View home, running, liveBar;
    private TextView liveText, nothingKept;
    private EditText address;
    private ListView keptList;
    private WebView web;
    private final List<String> logged = Collections.synchronizedList(new ArrayList<String>());   // what the app on screen has logged
    private String loggedBy = "";           // and which app that was
    private String host = "";               // the address (in here) of the app on screen
    private String title = "Visualised";    // and its name
    private String liveSource = "";         // where it is being fetched from, when it is not one kept on the phone
    private Device device;
    private boolean background;             // the app on screen asked to keep going when the phone is used for something else
    private ValueCallback<Uri[]> picking;
    private Uri photo;

    // ---------------------------------------------------------------- starting and stopping
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        apps = new Apps(this);
        prefs = getSharedPreferences("visualised", MODE_PRIVATE);
        FrameLayout root = new FrameLayout(this);
        running = buildRunning();
        home = buildHome();
        root.addView(running, new FrameLayout.LayoutParams(-1, -1));
        root.addView(home, new FrameLayout.LayoutParams(-1, -1));
        setContentView(root);
        showHome();
        opened(getIntent());
        if (!prefs.getBoolean("asked", false)) {        // once, the first time: everything an app might use, so apps aren't interrupted later
            prefs.edit().putBoolean("asked", true).apply();
            List<String> all = new ArrayList<>();
            all.add("android.permission.CAMERA");
            all.add("android.permission.RECORD_AUDIO");
            all.add("android.permission.ACCESS_FINE_LOCATION");
            all.add("android.permission.ACCESS_COARSE_LOCATION");
            if (Build.VERSION.SDK_INT >= 33) {
                all.add("android.permission.POST_NOTIFICATIONS");
            }
            requestPermissions(all.toArray(new String[0]), 99);
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        opened(intent);
    }

    /** Opened from a link (visualised://computer:number/), as the page the designer serves offers. Always asks first. */
    private void opened(Intent intent) {
        Uri link = intent == null ? null : intent.getData();
        if (intent != null && Intent.ACTION_SEND.equals(intent.getAction())) {
            sent((Uri) intent.getParcelableExtra(Intent.EXTRA_STREAM));    // shared to Visualised from another app
            return;
        }
        if (link != null && ("content".equals(link.getScheme()) || "file".equals(link.getScheme()))) {
            sent(link);                                 // a file opened with Visualised
            return;
        }
        if (link != null && "visualised-kept".equals(link.getScheme()) && link.getHost() != null) {
            for (Apps.Kept app : apps.all()) {          // an icon on the home screen for an app kept on this phone
                if (app.id.equals(link.getHost())) {
                    openKept(app);
                    return;
                }
            }
            Toast.makeText(this, "That app isn't on this phone any more.", Toast.LENGTH_LONG).show();
            return;
        }
        if (link == null || !"visualised".equals(link.getScheme()) || link.getHost() == null) {
            return;
        }
        final String where = Apps.address(link.getEncodedAuthority(), link.getEncodedPath());
        new AlertDialog.Builder(this)
                .setTitle("Open this app?")
                .setMessage("From " + link.getEncodedAuthority() + ".\n\nOnly open apps from a computer you know.")
                .setPositiveButton("Open", (d, w) -> openLive(where))
                .setNegativeButton("Cancel", null)
                .show();
    }

    /** An app's page that reached this phone as a file: sent by a friend, or saved from a message. Always asks first. */
    private void sent(final Uri file) {
        if (file == null) {
            return;
        }
        new AlertDialog.Builder(this)
                .setTitle("Keep this app on this phone?")
                .setMessage("It was sent to this phone as a file.\n\nOnly keep apps from someone you know.")
                .setPositiveButton("Keep", (d, w) -> new Thread(() -> {
                    try {
                        byte[] page;
                        try (InputStream in = getContentResolver().openInputStream(file)) {
                            if (in == null) {
                                throw new IOException("That file couldn't be read.");
                            }
                            page = Apps.readAll(in, 64 * 1024 * 1024);
                        }
                        final Apps.Kept got = apps.keepSent(page);
                        main.post(() -> {
                            Toast.makeText(this, got.name + " is on this phone. Press and hold it in the list to give it an icon "
                                    + "on the home screen, or to send it on.", Toast.LENGTH_LONG).show();
                            showHome();
                            openKept(got);
                        });
                    } catch (final Exception e) {
                        main.post(() -> new AlertDialog.Builder(this).setTitle("That couldn't be kept")
                                .setMessage(e instanceof IOException && e.getMessage() != null ? e.getMessage() : "That file couldn't be read.")
                                .setPositiveButton("OK", null).show());
                    }
                }).start())
                .setNegativeButton("Cancel", null)
                .show();
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (!background) {
            // An app that isn't on screen lets go of the camera and its light, or nothing else on the phone can use them.
            web.evaluateJavascript("window.vmlAway&&window.vmlAway()", null);
            web.onPause();
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
    }

    @Override
    protected void onDestroy() {
        runInBackground(false);
        device.close();
        web.destroy();
        super.onDestroy();
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (home.getVisibility() != View.VISIBLE) {
            showHome();
        } else {
            super.onBackPressed();
        }
    }

    // ---------------------------------------------------------------- the first screen
    private int dp(float n) {
        return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, n, getResources().getDisplayMetrics()));
    }

    private TextView words(String text, float size, int colour, boolean bold) {
        TextView t = new TextView(this);
        t.setText(text);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, size);
        t.setTextColor(colour);
        if (bold) {
            t.setTypeface(Typeface.DEFAULT_BOLD);
        }
        return t;
    }

    private View buildHome() {
        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setBackgroundColor(Color.WHITE);

        LinearLayout head = new LinearLayout(this);
        head.setOrientation(LinearLayout.VERTICAL);
        head.setBackgroundColor(BRAND);
        head.setPadding(dp(20), dp(22), dp(20), dp(20));
        head.addView(words("Visualised", 26, Color.WHITE, true));
        head.addView(words("The apps you've made, on your phone.", 14, 0xFFDBE4FF, false));
        String version = "";
        try {
            version = getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
        } catch (PackageManager.NameNotFoundException ignored) {
            // then it isn't shown
        }
        TextView ver = words("Version " + version, 12, 0xFFA5B4FC, false);
        ver.setPadding(0, dp(6), 0, 0);
        head.addView(ver);
        page.addView(head, new LinearLayout.LayoutParams(-1, -2));

        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(dp(20), dp(18), dp(20), 0);
        body.addView(words("From your computer", 16, 0xFF111827, true));
        TextView how = words("In the designer choose View, then Preview on Phone, and scan the code with this phone's camera. "
                + "Or type the address it shows here, or the web address of an app someone has published.", 14, 0xFF4B5563, false);
        how.setPadding(0, dp(4), 0, dp(10));
        body.addView(how);

        LinearLayout row = new LinearLayout(this);
        row.setGravity(Gravity.CENTER_VERTICAL);
        address = new EditText(this);
        address.setHint("192.168.1.20:8000 or a web address");
        address.setSingleLine(true);
        address.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        address.setImeOptions(EditorInfo.IME_ACTION_GO);
        address.setText(prefs.getString("address", ""));
        address.setOnEditorActionListener((v, action, event) -> {
            openTyped();
            return true;
        });
        Button open = new Button(this);
        open.setText("Open");
        open.setOnClickListener(v -> openTyped());
        row.addView(address, new LinearLayout.LayoutParams(0, -2, 1));
        row.addView(open, new LinearLayout.LayoutParams(-2, -2));
        body.addView(row);

        TextView kept = words("On this phone", 16, 0xFF111827, true);
        kept.setPadding(0, dp(22), 0, dp(4));
        body.addView(kept);
        nothingKept = words("Nothing kept yet. Open an app from your computer, then choose Keep on this phone: "
                + "after that it runs anywhere, with the computer off, and can have an icon of its own on the home screen.", 14, 0xFF4B5563, false);
        body.addView(nothingKept);
        Button file = new Button(this, null, android.R.attr.borderlessButtonStyle);
        file.setText("Open an app someone sent you");
        file.setAllCaps(false);
        file.setTextColor(BRAND);
        file.setPadding(0, 0, 0, 0);
        file.setGravity(Gravity.START | Gravity.CENTER_VERTICAL);
        file.setOnClickListener(v -> {
            try {
                startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("text/html"), SENT);
            } catch (ActivityNotFoundException e) {
                Toast.makeText(this, "This phone has nothing to choose a file with.", Toast.LENGTH_LONG).show();
            }
        });
        body.addView(file, new LinearLayout.LayoutParams(-1, -2));
        page.addView(body, new LinearLayout.LayoutParams(-1, -2));

        keptList = new ListView(this);
        keptList.setPadding(dp(6), 0, dp(6), 0);
        keptList.setOnItemClickListener((parent, view, at, id) -> openKept((Apps.Kept) parent.getItemAtPosition(at)));
        keptList.setOnItemLongClickListener((parent, view, at, id) -> {
            keptMenu((Apps.Kept) parent.getItemAtPosition(at));
            return true;
        });
        page.addView(keptList, new LinearLayout.LayoutParams(-1, 0, 1));
        return page;
    }

    private void showHome() {
        web.loadUrl("about:blank");                     // stops the app that was running: its timers, its camera
        host = "";
        liveSource = "";
        runInBackground(false);
        device.reset();
        getWindow().clearFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        List<Apps.Kept> all = apps.all();
        keptList.setAdapter(new ArrayAdapter<Apps.Kept>(this, android.R.layout.simple_list_item_1, new ArrayList<>(all)) {
            @Override
            public View getView(int at, View old, ViewGroup parent) {
                Apps.Kept app = getItem(at);
                LinearLayout row = new LinearLayout(MainActivity.this);
                row.setGravity(Gravity.CENTER_VERTICAL);
                row.setPadding(dp(14), dp(10), dp(14), dp(10));
                ImageView picture = new ImageView(MainActivity.this);
                picture.setImageBitmap(iconFor(app, dp(44), false));
                row.addView(picture, new LinearLayout.LayoutParams(dp(44), dp(44)));
                LinearLayout words = new LinearLayout(MainActivity.this);
                words.setOrientation(LinearLayout.VERTICAL);
                words.setPadding(dp(14), 0, 0, 0);
                words.addView(words(app.name, 16, 0xFF111827, true));
                String kept = DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.SHORT).format(new Date(app.when));
                words.addView(words((app.version.isEmpty() ? "" : "Version " + app.version + "  \u00b7  ") + "kept " + kept, 13, 0xFF6B7280, false));
                row.addView(words, new LinearLayout.LayoutParams(0, -2, 1));
                return row;
            }
        });
        nothingKept.setVisibility(all.isEmpty() ? View.VISIBLE : View.GONE);
        home.setVisibility(View.VISIBLE);
        running.setVisibility(View.INVISIBLE);
        bar(BRAND);
        device.brightness(-1);                          // a screen an app turned up goes back to the phone's own
    }

    private void keptMenu(final Apps.Kept app) {
        boolean canFetch = !app.source.isEmpty();
        List<String> offered = new ArrayList<>(java.util.Arrays.asList("Open", "Add to the home screen", "Share with someone here"));
        if (canFetch) {
            offered.add("Fetch the newest from where it came from");
        }
        if (app.name.equals(loggedBy) && !logged.isEmpty()) {
            offered.add("See what it logged");
        }
        offered.add("Remove from this phone");
        final String[] choices = offered.toArray(new String[0]);
        new AlertDialog.Builder(this).setTitle(app.name).setItems(choices, (d, which) -> {
            String chosen = choices[which];
            if (chosen.startsWith("Open")) {
                openKept(app);
            } else if (chosen.startsWith("Add")) {
                addToHomeScreen(app);
            } else if (chosen.startsWith("Share")) {
                shareMenu(app);
            } else if (chosen.startsWith("See")) {
                showLog();
            } else if (chosen.startsWith("Fetch")) {
                keep(app.source, app.id);
            } else {
                new AlertDialog.Builder(this)
                        .setTitle("Remove " + app.name + "?")
                        .setMessage("The app goes from this phone. Anything it saved here goes when Visualised itself is removed.")
                        .setPositiveButton("Remove", (dd, w) -> {
                            ShortcutManager icons = getSystemService(ShortcutManager.class);
                            if (icons != null) {        // its icon on the home screen, if it has one, stops working and says why
                                icons.disableShortcuts(Collections.singletonList("kept-" + app.id), "This app was removed from Visualised.");
                            }
                            apps.remove(app.id);
                            showHome();
                        })
                        .setNegativeButton("Cancel", null).show();
            }
        }).show();
    }

    // ---------------------------------------------------------------- what an app logged, for whoever made it
    void log(String text) {
        logged.add(DateFormat.getTimeInstance(DateFormat.MEDIUM).format(new Date()) + "  " + text);
        while (logged.size() > 300) {
            logged.remove(0);
        }
    }

    /** The lines the last app run wrote with Vml("Log", ...), to read here or send somewhere. */
    private void showLog() {
        final String all;
        synchronized (logged) {
            all = logged.isEmpty() ? "Nothing has been logged." : android.text.TextUtils.join("\n\n", logged);
        }
        TextView text = words(all, 12, 0xFF111827, false);
        text.setTextIsSelectable(true);
        text.setTypeface(Typeface.MONOSPACE);
        text.setPadding(dp(20), dp(8), dp(20), dp(8));
        android.widget.ScrollView scroll = new android.widget.ScrollView(this);
        scroll.addView(text);
        new AlertDialog.Builder(this).setTitle("Logged by " + loggedBy).setView(scroll)
                .setPositiveButton("Send it", (d, w) -> device.share(all, "Log from " + loggedBy))
                .setNegativeButton("Close", null)
                .show();
    }

    // ---------------------------------------------------------------- handing an app to a friend
    /**
     * Three ways to hand an app over. Sending it is the one for two people stood together: the phone's own
     * sharing (Quick Share) finds the other phone and passes the files across with no internet and no Wi-Fi in
     * common. Visualised itself can go along for a friend who hasn't got it.
     */
    private void shareMenu(final Apps.Kept app) {
        final String[] ways = {"Send it to their phone", "Send it, and Visualised too", "Show a code to scan"};
        new AlertDialog.Builder(this).setTitle("Share " + app.name).setItems(ways, (d, which) -> {
            if (which == 2) {
                shareHere(app);
                return;
            }
            final boolean both = which == 1;
            new AlertDialog.Builder(this).setTitle(both ? "Sending both" : "Sending " + app.name)
                    .setMessage("Next, pick Quick Share and then their phone. It needs no internet.\n\nOn their phone"
                            + (both ? ": open Visualised.apk first, to install Visualised. Then open " : ": open ")
                            + "the other file, " + Given.app(app).getLastPathSegment() + ", choose Visualised to open it, and press Keep.")
                    .setPositiveButton("Send", (dd, w) -> send(app, both))
                    .setNegativeButton("Cancel", null).show();
        }).show();
    }

    private void send(Apps.Kept app, boolean withVisualised) {
        ArrayList<Uri> files = new ArrayList<>();
        if (withVisualised) {
            files.add(Given.visualised());
        }
        files.add(Given.app(app));
        Intent send;
        if (files.size() == 1) {
            send = new Intent(Intent.ACTION_SEND).setType("text/html").putExtra(Intent.EXTRA_STREAM, files.get(0));
        } else {
            send = new Intent(Intent.ACTION_SEND_MULTIPLE).setType("*/*").putParcelableArrayListExtra(Intent.EXTRA_STREAM, files);
        }
        ClipData lent = ClipData.newRawUri(app.name, files.get(0));     // what the receiving app is allowed to read
        for (int i = 1; i < files.size(); i++) {
            lent.addItem(new ClipData.Item(files.get(i)));
        }
        send.setClipData(lent);
        send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        try {
            startActivity(Intent.createChooser(send, "Send " + app.name).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION));
        } catch (ActivityNotFoundException e) {
            Toast.makeText(this, "This phone has nothing to send files with.", Toast.LENGTH_LONG).show();
        }
    }

    /**
     * Show a QR code a friend's phone can point its camera at to get this app. An app that came from a web site
     * is shared by its address, which works anywhere. One that didn't (made on the owner's own computer) is
     * handed over directly: this phone serves the page for as long as the code is on screen, to phones on the
     * same Wi-Fi (or joined to this phone's hotspot). Nothing goes over the internet.
     */
    private void shareHere(final Apps.Kept app) {
        Uri from = Uri.parse(app.source);
        boolean onTheWeb = "https".equals(from.getScheme()) && from.getHost() != null && from.getHost().contains(".")
                && !from.getHost().matches("[0-9.]+") && !from.getHost().endsWith(".local");
        final Sharer sharer;
        final String link;
        String how;
        if (onTheWeb) {
            sharer = null;
            // By way of a page that explains itself: it offers Visualised to a phone that hasn't got it, opens the
            // app in Visualised on one that has, and runs it in the browser on anything else.
            String landing = "https://visualised.io/open.html#" + app.source;
            link = landing.length() <= 200 ? landing : app.source;
            how = "Ask them to point their camera at this. It works anywhere.";
        } else {
            String here = Sharer.address();
            if (here == null) {
                new AlertDialog.Builder(this).setTitle("Share " + app.name)
                        .setMessage("To hand this app over, both phones need to be on the same Wi-Fi. If there isn't one, turn on "
                                + "this phone's hotspot, have them join it, and try again.")
                        .setPositiveButton("OK", null).show();
                return;
            }
            try {
                sharer = new Sharer(apps.page(app.id), new File(getApplicationInfo().sourceDir));
            } catch (IOException e) {
                Toast.makeText(this, "This phone couldn't start sharing.", Toast.LENGTH_LONG).show();
                return;
            }
            link = "http://" + here + ":" + sharer.port() + "/";
            how = "Ask them to point their camera at this while it is on screen. No internet is needed, but their phone has to "
                    + "be able to reach this one: both on the same Wi-Fi, or, surest of all, turn on this phone's hotspot and have "
                    + "them join it, then share again. Keep this open until they have pressed Keep on this phone.";
        }
        boolean[][] code = Qr.matrix(link);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER_HORIZONTAL);
        box.setPadding(dp(20), dp(8), dp(20), 0);
        if (code != null) {
            int side = Math.min(getResources().getDisplayMetrics().widthPixels - dp(120), dp(280)), dot = Math.max(2, side / (code.length + 8));
            Bitmap picture = Bitmap.createBitmap(dot * (code.length + 8), dot * (code.length + 8), Bitmap.Config.RGB_565);
            Canvas canvas = new Canvas(picture);
            canvas.drawColor(Color.WHITE);              // with the quiet margin a scanner needs
            Paint ink = new Paint();
            ink.setColor(Color.BLACK);
            for (int y = 0; y < code.length; y++) {
                for (int x = 0; x < code.length; x++) {
                    if (code[y][x]) {
                        canvas.drawRect((x + 4) * dot, (y + 4) * dot, (x + 5) * dot, (y + 5) * dot, ink);
                    }
                }
            }
            ImageView shown = new ImageView(this);
            shown.setImageBitmap(picture);
            box.addView(shown, new LinearLayout.LayoutParams(picture.getWidth(), picture.getHeight()));
        }
        TextView address = words(sharer == null ? app.source : link, 14, 0xFF111827, true);
        address.setTextIsSelectable(true);
        address.setPadding(0, dp(8), 0, dp(6));
        box.addView(address);
        box.addView(words(how + "\n\nIf they haven't got Visualised, the page they land on offers it"
                + (sharer != null ? ", straight from this phone." : "."), 13, 0xFF4B5563, false));
        new AlertDialog.Builder(this).setTitle("Share " + app.name).setView(box)
                .setPositiveButton("Done", null)
                .setOnDismissListener(d -> {
                    if (sharer != null) {
                        sharer.close();
                    }
                })
                .show();
    }

    /** Offer an icon of its own on the phone's home screen for an app kept here: one tap and it is running. */
    private void addToHomeScreen(Apps.Kept app) {
        ShortcutManager icons = getSystemService(ShortcutManager.class);
        if (icons == null || !icons.isRequestPinShortcutSupported()) {
            Toast.makeText(this, "This phone's home screen doesn't take icons from apps.", Toast.LENGTH_LONG).show();
            return;
        }
        Intent open = new Intent(this, MainActivity.class).setAction(Intent.ACTION_VIEW).setData(Uri.parse("visualised-kept://" + app.id));
        ShortcutInfo icon = new ShortcutInfo.Builder(this, "kept-" + app.id)
                .setShortLabel(app.name)
                .setLongLabel(app.name)
                .setIcon(Icon.createWithAdaptiveBitmap(iconFor(app, dp(108), true)))
                .setIntent(open)
                .build();
        icons.requestPinShortcut(icon, null);            // the phone asks the user where to put it
    }

    /**
     * An app's icon: its own picture if the form was given one, else its first letter on a colour. padded: for the
     * home screen, where the phone cuts its own shape out of the middle, so the picture is kept clear of the edges.
     */
    private Bitmap iconFor(Apps.Kept app, int size, boolean padded) {
        Bitmap own = app.icon == null ? null : BitmapFactory.decodeFile(app.icon.getPath());
        if (own == null) {
            Bitmap letter = letterIcon(app.name, padded ? size : Math.round(size * 1.6f));
            if (padded) {
                return letter;
            }
            int cut = (letter.getWidth() - size) / 2;   // the letter fills a list's picture; a home screen's has room round it
            return Bitmap.createBitmap(letter, cut, cut, size, size);
        }
        Bitmap picture = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(picture);
        Paint smooth = new Paint(Paint.FILTER_BITMAP_FLAG | Paint.ANTI_ALIAS_FLAG);
        if (padded) {
            canvas.drawColor(own.getPixel(0, 0) >>> 24 == 0xFF ? own.getPixel(0, 0) : Color.WHITE);    // carry the picture's own edge colour outward
        }
        float inner = padded ? size * 0.62f : size, edge = (size - inner) / 2f;
        canvas.drawBitmap(own, null, new RectF(edge, edge, edge + inner, edge + inner), smooth);
        return picture;
    }

    /** An icon for an app that hasn't one of its own: its first letter on a colour that is always the same for that name. */
    private Bitmap letterIcon(String name, int size) {
        Bitmap picture = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(picture);
        int[] colours = {0xFF1E3A8A, 0xFF0F766E, 0xFF9D174D, 0xFF7C3AED, 0xFFB45309, 0xFF15803D, 0xFF0369A1, 0xFFBE123C};
        canvas.drawColor(colours[Math.abs(name.toLowerCase().hashCode() % colours.length)]);
        Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        paint.setColor(Color.WHITE);
        paint.setTypeface(Typeface.DEFAULT_BOLD);
        paint.setTextAlign(Paint.Align.CENTER);
        paint.setTextSize(size * 0.36f);
        String letter = name.trim().isEmpty() ? "V" : name.trim().substring(0, name.trim().offsetByCodePoints(0, 1)).toUpperCase();
        canvas.drawText(letter, size / 2f, size / 2f - (paint.descent() + paint.ascent()) / 2f, paint);
        return picture;
    }

    // ---------------------------------------------------------------- opening apps
    private void openTyped() {
        String typed = address.getText().toString().trim();
        if (typed.isEmpty()) {
            return;
        }
        if (typed.startsWith("visualised://")) {
            typed = typed.substring("visualised://".length());
        }
        if (!typed.contains("://")) {
            int slash = typed.indexOf('/');
            typed = Apps.address(slash < 0 ? typed : typed.substring(0, slash), slash < 0 ? "/" : typed.substring(slash));
        }
        Uri u = Uri.parse(typed);
        if (u.getHost() == null || !("http".equals(u.getScheme()) || "https".equals(u.getScheme()))) {
            Toast.makeText(this, "That doesn't look like an address. It is like 192.168.1.20:8000", Toast.LENGTH_LONG).show();
            return;
        }
        prefs.edit().putString("address", address.getText().toString().trim()).apply();
        openLive(typed);
    }

    /** Run the app a computer is serving, fetched afresh each time. */
    private void openLive(String where) {
        Uri u = Uri.parse(where);
        String base = u.getScheme() + "://" + u.getEncodedAuthority();
        String name = "live-" + Apps.safe(u.getEncodedAuthority().replace('.', '-').replace(':', '-')) + SUFFIX;
        live.put(name, base);
        liveSource = where;
        liveText.setText("Live from " + u.getEncodedAuthority());
        liveBar.setVisibility(View.VISIBLE);
        String path = u.getEncodedPath() == null || u.getEncodedPath().isEmpty() ? "/" : u.getEncodedPath();
        show(name, u.getEncodedAuthority(), path);
    }

    private void openKept(Apps.Kept app) {
        liveSource = "";
        liveBar.setVisibility(View.GONE);
        show(app.id + SUFFIX, app.name, "/");
    }

    private void show(String name, String called, String path) {
        host = name;
        title = called;
        logged.clear();
        loggedBy = called;
        device.warmVoice();
        home.setVisibility(View.INVISIBLE);
        running.setVisibility(View.VISIBLE);
        web.clearHistory();
        web.loadUrl("https://" + name + path);
    }

    /** Fetch the app at an address and keep it on the phone (in place of the one already kept, when given). */
    private void keep(final String where, final String replace) {
        Toast.makeText(this, "Fetching…", Toast.LENGTH_SHORT).show();
        new Thread(() -> {
            try {
                final Apps.Kept got = apps.keep(where, replace);
                main.post(() -> {
                    Toast.makeText(this, replace == null
                            ? got.name + " is on this phone. Press and hold it in the list to give it an icon on the home screen."
                            : got.name + " on this phone is now the newest" + (got.version.isEmpty() ? "." : ": version " + got.version + "."), Toast.LENGTH_LONG).show();
                    openKept(got);
                });
            } catch (final Exception e) {
                main.post(() -> new AlertDialog.Builder(this)
                        .setTitle("That couldn't be fetched")
                        .setMessage(reason(e) + "\n\nFor an app on your own computer, the phone and the computer need to be "
                                + "on the same network, with Preview on Phone open in the designer.")
                        .setPositiveButton("OK", null).show());
            }
        }).start();
    }

    private static String reason(Exception e) {
        String m = e.getMessage();
        return m == null || m.isEmpty() ? "The computer didn't answer." : m;
    }

    // ---------------------------------------------------------------- the running app
    @SuppressLint("SetJavaScriptEnabled")
    private View buildRunning() {
        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setBackgroundColor(Color.WHITE);

        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setGeolocationEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(false);
        s.setTextZoom(100);                             // forms are drawn to the pixel: the phone's text size mustn't push them about
        s.setSupportMultipleWindows(false);
        device = new Device(this);
        web.addJavascriptInterface(device, "VisualisedDevice");
        web.setWebViewClient(new Pages());
        web.setWebChromeClient(new Asks());
        page.addView(web, new LinearLayout.LayoutParams(-1, 0, 1));

        LinearLayout strip = new LinearLayout(this);
        strip.setGravity(Gravity.CENTER_VERTICAL);
        strip.setBackgroundColor(0xFFF3F4F6);
        strip.setPadding(dp(12), 0, dp(4), 0);
        liveText = words("", 13, 0xFF374151, false);
        liveText.setSingleLine(true);
        liveText.setOnLongClickListener(v -> {      // for whoever is making the app: what it has logged so far
            showLog();
            return true;
        });
        Button again = new Button(this, null, android.R.attr.borderlessButtonStyle);
        again.setText("Refresh");
        again.setOnClickListener(v -> web.reload());
        Button keepIt = new Button(this, null, android.R.attr.borderlessButtonStyle);
        keepIt.setText("Keep on this phone");
        keepIt.setOnClickListener(v -> {
            if (!liveSource.isEmpty()) {
                Apps.Kept already = apps.from(liveSource);          // kept before from here: this one takes its place, icon and all
                keep(liveSource, already == null ? null : already.id);
            }
        });
        strip.addView(liveText, new LinearLayout.LayoutParams(0, -2, 1));
        strip.addView(again, new LinearLayout.LayoutParams(-2, -2));
        strip.addView(keepIt, new LinearLayout.LayoutParams(-2, -2));
        liveBar = strip;
        page.addView(strip, new LinearLayout.LayoutParams(-1, -2));
        return page;
    }

    /** The colour of the strip at the very top of the screen, with its clock and icons dark or light to suit. */
    @SuppressWarnings("deprecation")
    private void bar(int colour) {
        getWindow().setStatusBarColor(colour);
        double light = (0.299 * Color.red(colour) + 0.587 * Color.green(colour) + 0.114 * Color.blue(colour)) / 255;
        View v = getWindow().getDecorView();
        int flags = v.getSystemUiVisibility();
        v.setSystemUiVisibility(light > 0.6 ? flags | View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR : flags & ~View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);
    }

    /** Answers every request an app's page makes, and keeps the page from wandering off to other sites. */
    private final class Pages extends WebViewClient {
        @Override
        public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
            Uri u = request.getUrl();
            String name = u.getHost();
            if (name == null || !name.endsWith(SUFFIX)) {
                return null;                            // something on the real web the page asked for (a picture, a map)
            }
            String path = u.getEncodedPath() == null || u.getEncodedPath().isEmpty() ? "/" : u.getEncodedPath();
            String base = live.get(name);
            try {
                if (base == null) {
                    File page = apps.page(name.substring(0, name.length() - SUFFIX.length()));
                    if (("/".equals(path) || "/index.html".equals(path)) && page.isFile()) {
                        return answer(200, "text/html", "utf-8", new FileInputStream(page));
                    }
                    return said(404, "That isn't part of this app.");
                }
                String query = u.getEncodedQuery();
                Map<String, String> asked = new HashMap<>();
                for (Map.Entry<String, String> h : request.getRequestHeaders().entrySet()) {
                    if (!"Origin".equalsIgnoreCase(h.getKey()) && !"Referer".equalsIgnoreCase(h.getKey())) {
                        asked.put(h.getKey(), h.getValue());
                    }
                }
                HttpURLConnection c = Apps.open(base + path + (query == null ? "" : "?" + query), asked, 20000);
                int code = c.getResponseCode();
                InputStream in = code >= 400 ? c.getErrorStream() : c.getInputStream();
                if (in == null) {
                    in = new ByteArrayInputStream(new byte[0]);
                }
                if (code < 200 || (code >= 300 && code < 400)) {
                    code = 502;
                }
                String type = c.getContentType(), charset = null;
                if (type == null) {
                    type = URLConnection.guessContentTypeFromName(path);
                }
                if (type == null) {
                    type = "/".equals(path) ? "text/html" : "application/octet-stream";
                }
                int semi = type.indexOf(';');
                if (semi >= 0) {
                    int cs = type.toLowerCase().indexOf("charset=");
                    if (cs >= 0) {
                        charset = type.substring(cs + 8).trim().replace("\"", "");
                    }
                    type = type.substring(0, semi).trim();
                }
                if (charset == null && type.startsWith("text/")) {
                    charset = "utf-8";
                }
                return answer(code, type, charset, in);
            } catch (IOException e) {
                return said(503, "No answer from " + Uri.parse(base).getEncodedAuthority() + ".\n\nFor an app on your own computer, "
                        + "the phone and the computer need to be on the same network, with Preview on Phone open in the designer. "
                        + "Then press Refresh.");
            }
        }

        private WebResourceResponse answer(int code, String type, String charset, InputStream in) {
            Map<String, String> headers = new HashMap<>();
            headers.put("Cache-Control", "no-store");
            return new WebResourceResponse(type, charset, code, code == 200 ? "OK" : "Error", headers, in);
        }

        private WebResourceResponse said(int code, String text) {
            String html = "<!DOCTYPE html><meta name=viewport content='width=device-width, initial-scale=1'>"
                    + "<body style='font:16px sans-serif;color:#374151;padding:28px;white-space:pre-wrap'>"
                    + text.replace("&", "&amp;").replace("<", "&lt;") + "</body>";
            return answer(code, "text/html", "utf-8", new ByteArrayInputStream(html.getBytes(StandardCharsets.UTF_8)));
        }

        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            Uri u = request.getUrl();
            if (host.equals(u.getHost()) || "about".equals(u.getScheme())) {
                return false;
            }
            String scheme = u.getScheme() == null ? "" : u.getScheme();
            if (scheme.equals("http") || scheme.equals("https") || scheme.equals("mailto") || scheme.equals("tel")
                    || scheme.equals("sms") || scheme.equals("geo")) {
                try {                                   // a link to somewhere else opens in the phone's own app for it
                    startActivity(new Intent(Intent.ACTION_VIEW, u));
                } catch (ActivityNotFoundException ignored) {
                    Toast.makeText(MainActivity.this, "Nothing on this phone opens that.", Toast.LENGTH_SHORT).show();
                }
            }
            return true;
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            if (host.isEmpty() || url == null || !url.contains(SUFFIX)) {
                return;
            }
            view.evaluateJavascript("(function(){var m=document.querySelector('meta[name=theme-color]'),v=document.querySelector('meta[name=app-version]');"
                    + "return [m?m.content:'',document.title||'',v?v.content:''].join('\\n')})()", value -> {
                if (value == null || host.isEmpty()) {
                    return;
                }
                String[] got = value.replaceAll("^\"|\"$", "").split("\\\\n", 3);
                try {                                   // (a page that names no colour of its own gets the app's)
                    bar(got[0].trim().isEmpty() ? BRAND : Color.parseColor(got[0].trim()));
                } catch (RuntimeException e) {
                    bar(BRAND);
                }
                if (got.length > 1 && !got[1].trim().isEmpty()) {
                    title = got[1].trim();
                }
                if (!liveSource.isEmpty()) {            // so you can tell at a glance that the newest has arrived
                    String from = Uri.parse(liveSource).getEncodedAuthority();
                    String at = DateFormat.getTimeInstance(DateFormat.MEDIUM).format(new Date());
                    liveText.setText((got.length > 2 && !got[2].trim().isEmpty() ? "v" + got[2].trim() + "  \u00b7  " : "") + "fetched " + at + " from " + from);
                }
            });
        }
    }

    /** What a page asks the user or the phone for: messages, location, the camera, a file. */
    private final class Asks extends WebChromeClient {
        @Override
        public boolean onJsAlert(WebView view, String url, String message, final JsResult result) {
            new AlertDialog.Builder(MainActivity.this).setTitle(title).setMessage(message)
                    .setPositiveButton("OK", (d, w) -> result.confirm())
                    .setOnCancelListener(d -> result.cancel()).show();
            return true;
        }

        @Override
        public boolean onJsConfirm(WebView view, String url, String message, final JsResult result) {
            new AlertDialog.Builder(MainActivity.this).setTitle(title).setMessage(message)
                    .setPositiveButton("OK", (d, w) -> result.confirm())
                    .setNegativeButton("Cancel", (d, w) -> result.cancel())
                    .setOnCancelListener(d -> result.cancel()).show();
            return true;
        }

        @Override
        public boolean onJsPrompt(WebView view, String url, String message, String value, final JsPromptResult result) {
            final EditText box = new EditText(MainActivity.this);
            box.setSingleLine(true);
            box.setText(value == null ? "" : value);
            FrameLayout pad = new FrameLayout(MainActivity.this);
            pad.setPadding(dp(20), 0, dp(20), 0);
            pad.addView(box);
            new AlertDialog.Builder(MainActivity.this).setTitle(title).setMessage(message).setView(pad)
                    .setPositiveButton("OK", (d, w) -> result.confirm(box.getText().toString()))
                    .setNegativeButton("Cancel", (d, w) -> result.cancel())
                    .setOnCancelListener(d -> result.cancel()).show();
            return true;
        }

        @Override
        public void onGeolocationPermissionsShowPrompt(final String origin, final GeolocationPermissions.Callback callback) {
            withPermission(new String[]{"android.permission.ACCESS_FINE_LOCATION", "android.permission.ACCESS_COARSE_LOCATION"},
                    granted -> callback.invoke(origin, granted, false));
        }

        @Override
        public void onPermissionRequest(final PermissionRequest request) {
            String from = request.getOrigin() == null ? null : request.getOrigin().getHost();
            if (from == null || !from.equals(host)) {
                request.deny();
                return;
            }
            final List<String[]> wanted = new ArrayList<>();        // what the page asked for, with the permission each needs
            for (String r : request.getResources()) {
                if (PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(r)) {
                    wanted.add(new String[]{r, "android.permission.CAMERA"});
                } else if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(r)) {
                    wanted.add(new String[]{r, "android.permission.RECORD_AUDIO"});
                }
            }
            grantNext(request, wanted, 0, new ArrayList<>());
        }

        /** Ask for the camera, then the microphone, one at a time; the page gets whichever the user allowed. */
        private void grantNext(final PermissionRequest request, final List<String[]> wanted, final int at, final List<String> allowed) {
            if (at >= wanted.size()) {
                if (allowed.isEmpty()) {
                    request.deny();
                } else {
                    request.grant(allowed.toArray(new String[0]));
                }
                return;
            }
            withPermission(new String[]{wanted.get(at)[1]}, granted -> {
                if (granted) {
                    allowed.add(wanted.get(at)[0]);
                }
                grantNext(request, wanted, at + 1, allowed);
            });
        }

        @Override
        public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, final FileChooserParams params) {
            if (picking != null) {
                picking.onReceiveValue(null);
            }
            picking = callback;
            boolean pictures = params.getAcceptTypes() == null || params.getAcceptTypes().length == 0;
            if (!pictures) {
                for (String t : params.getAcceptTypes()) {
                    pictures |= t == null || t.isEmpty() || t.startsWith("image/") || t.equals("*/*");
                }
            }
            if (pictures && getPackageManager().hasSystemFeature(PackageManager.FEATURE_CAMERA_ANY)) {
                withPermission(new String[]{"android.permission.CAMERA"}, granted -> choose(params, granted));
            } else {
                choose(params, false);
            }
            return true;
        }
    }

    /** Let the user pick a file for the page, or (when allowed) take a photo for it there and then. */
    @SuppressWarnings("deprecation")
    private void choose(WebChromeClient.FileChooserParams params, boolean camera) {
        Intent take = null;
        photo = null;
        if (camera) {
            try {
                ContentValues about = new ContentValues();
                about.put(MediaStore.Images.Media.DISPLAY_NAME, "visualised-" + System.currentTimeMillis() + ".jpg");
                about.put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg");
                photo = getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, about);
            } catch (RuntimeException e) {
                photo = null;
            }
            if (photo != null) {
                take = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
                take.putExtra(MediaStore.EXTRA_OUTPUT, photo);
                take.setClipData(ClipData.newRawUri("", photo));
                take.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION | Intent.FLAG_GRANT_READ_URI_PERMISSION);
            }
        }
        try {
            if (take != null && params.isCaptureEnabled()) {
                startActivityForResult(take, PICK);
                return;
            }
            Intent chooser = Intent.createChooser(params.createIntent(), null);
            if (take != null) {
                chooser.putExtra(Intent.EXTRA_INITIAL_INTENTS, new Intent[]{take});
            }
            startActivityForResult(chooser, PICK);
        } catch (ActivityNotFoundException e) {
            picked(null);
        }
    }

    @Override
    @SuppressWarnings("deprecation")
    protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == LISTEN) {
            ArrayList<String> words = result == RESULT_OK && data != null ? data.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS) : null;
            if (words != null && !words.isEmpty() && !words.get(0).trim().isEmpty()) {
                tell("listen", words.get(0), "");
            } else {
                tell("listen", "", "Nothing was heard.");
            }
            return;
        }
        if (request == SENT) {
            if (result == RESULT_OK && data != null) {
                sent(data.getData());
            }
            return;
        }
        if (request != PICK) {
            return;
        }
        Uri[] files = null;
        if (result == RESULT_OK) {
            files = WebChromeClient.FileChooserParams.parseResult(result, data);
            if ((files == null || files.length == 0) && data != null && data.getClipData() != null) {
                ClipData many = data.getClipData();
                files = new Uri[many.getItemCount()];
                for (int i = 0; i < files.length; i++) {
                    files[i] = many.getItemAt(i).getUri();
                }
            }
            if ((files == null || files.length == 0) && photo != null) {
                files = new Uri[]{photo};               // the camera was used: the photo is where it was told to put it
                photo = null;
            }
        }
        picked(files);
    }

    private void picked(Uri[] files) {
        if (photo != null) {                            // a place was made for a photo that was never taken
            try {
                getContentResolver().delete(photo, null, null);
            } catch (RuntimeException ignored) {
                // nothing lost
            }
            photo = null;
        }
        if (picking != null) {
            picking.onReceiveValue(files);
            picking = null;
        }
    }

    // ---------------------------------------------------------------- answering the page later
    /** Tell the page on screen the answer to something that took a while (what was heard, a signal finished). */
    void tell(final String what, final String a, final String b) {
        runOnUiThread(() -> {
            if (!host.isEmpty()) {
                web.evaluateJavascript("window.vmlFromPhone&&window.vmlFromPhone(" + JSONObject.quote(what) + ","
                        + JSONObject.quote(a) + "," + JSONObject.quote(b) + ")", null);
            }
        });
    }

    /** Ask the phone's own speech recogniser what the user says; the page hears back through tell("listen", ...). */
    @SuppressWarnings("deprecation")
    void listen(String prompt) {
        Intent hear = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        hear.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        if (prompt != null && !prompt.isEmpty()) {
            hear.putExtra(RecognizerIntent.EXTRA_PROMPT, prompt);
        }
        try {
            startActivityForResult(hear, LISTEN);
        } catch (ActivityNotFoundException e) {
            tell("listen", "", "This phone has nothing to listen with.");
        }
    }

    /** Start or stop noting where a Bluetooth device connects and goes, asking for what that needs. */
    void watchBluetooth(final String address, final boolean on) {
        if (address == null || address.isEmpty()) {
            tell("watching", "stopped", "No device was chosen.");
            return;
        }
        if (!on) {
            Places.choose(this, address, false);
            tell("watching", "stopped", "");
            return;
        }
        final String[] bluetooth = Build.VERSION.SDK_INT >= 31 ? new String[]{"android.permission.BLUETOOTH_CONNECT"} : new String[0];
        withPermission(bluetooth, seen -> {
            if (!seen) {
                tell("watching", "stopped", "Seeing Bluetooth devices wasn't allowed.");
                return;
            }
            withPermission(new String[]{"android.permission.ACCESS_FINE_LOCATION", "android.permission.ACCESS_COARSE_LOCATION"}, located -> {
                if (!located) {
                    Places.choose(this, address, true);
                    tell("watching", "partly", "Location wasn't allowed, so only the time will be noted.");
                    return;
                }
                withPermission(Build.VERSION.SDK_INT >= 33 ? new String[]{"android.permission.POST_NOTIFICATIONS"} : new String[0], told -> {
                    if (Places.allowed(this, "android.permission.ACCESS_BACKGROUND_LOCATION")) {
                        Places.choose(this, address, true);
                        tell("watching", "watching", "");
                        return;
                    }
                    // Android asks this one on a settings page of its own, so the user is told what to pick there.
                    new AlertDialog.Builder(this)
                            .setTitle("One more thing")
                            .setMessage("To note where you parked while the phone is in your pocket, Android needs location "
                                    + "allowed all the time.\n\nOn the next screen choose \"Allow all the time\". It is used only "
                                    + "at the moment a device you chose disconnects, and what it notes stays on this phone.")
                            .setPositiveButton("Continue", (d, w) -> withPermission(new String[]{"android.permission.ACCESS_BACKGROUND_LOCATION"}, always -> {
                                Places.choose(this, address, true);
                                tell("watching", always ? "watching" : "partly", always ? "" : "Location isn't allowed all the time, so the place can only be noted while this app is open.");
                            }))
                            .setNegativeButton("Not now", (d, w) -> {
                                Places.choose(this, address, true);
                                tell("watching", "partly", "Location isn't allowed all the time, so the place can only be noted while this app is open.");
                            })
                            .show();
                });
            });
        });
    }

    // ---------------------------------------------------------------- running in the background
    /** Keep the app on screen going while the phone is used for something else (or stop doing so). */
    void runInBackground(boolean on) {
        if (on == background || (on && host.isEmpty())) {
            return;
        }
        background = on;
        if (!on) {
            stopService(new Intent(this, Running.class));
            return;
        }
        final String name = title;
        withPermission(Build.VERSION.SDK_INT >= 33 ? new String[]{"android.permission.POST_NOTIFICATIONS"} : new String[0], granted -> {
            if (background) {                           // with or without the notice being allowed to show
                startForegroundService(new Intent(this, Running.class).putExtra("name", name));
            }
        });
    }

    // ---------------------------------------------------------------- asking the user's permission
    /** Do something that needs the user's say-so: asks the first time, and tells the answer whether any was given. */
    void withPermission(String[] wanted, Answer answer) {
        boolean any = wanted.length == 0;
        for (String p : wanted) {
            any |= checkSelfPermission(p) == PackageManager.PERMISSION_GRANTED;
        }
        if (any) {
            answer.got(true);
            return;
        }
        int code = nextAsk++;
        asked.put(code, answer);
        requestPermissions(wanted, code);
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] wanted, int[] results) {
        super.onRequestPermissionsResult(code, wanted, results);
        Answer answer = asked.remove(code);
        if (answer == null) {
            return;
        }
        boolean any = false;
        for (int r : results) {
            any |= r == PackageManager.PERMISSION_GRANTED;
        }
        answer.got(any);
    }
}
