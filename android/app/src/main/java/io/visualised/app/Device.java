package io.visualised.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.ActivityNotFoundException;
import android.content.ContentValues;
import android.content.Intent;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraManager;
import android.net.ConnectivityManager;
import android.net.Uri;
import android.os.BatteryManager;
import android.os.SystemClock;
import android.provider.MediaStore;
import android.speech.tts.TextToSpeech;
import android.util.Base64;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.widget.Toast;

import java.io.IOException;
import java.io.OutputStream;
import java.net.URLConnection;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

import org.json.JSONException;
import org.json.JSONObject;

/**
 * What a Visualised app can ask of the phone beyond what any web page can. A page sees this as
 * window.VisualisedDevice, and the page's own Vml("Share", ...), Vml("Notify", ...) and the rest use it when it
 * is there. Everything else an app uses (location, the camera, vibration) is the web's own, which this app
 * switches on and asks permission for. Only pages the user opened in this app ever see this object.
 */
final class Device {
    private static final String CHANNEL = "apps";
    private final MainActivity activity;
    private int nextNote = 1;
    private TextToSpeech voice;
    private boolean voiceReady, torchOn;
    private String waitingToSay;
    private volatile Thread signalling;
    private SensorEventListener air;
    private volatile float pressureNow;

    private final Texts texts;

    Device(MainActivity activity) {
        this.activity = activity;
        this.texts = new Texts(activity);
    }

    /**
     * Ask a web address for something, away from the page (so no CORS, and it carries on with the screen off):
     * with no body a GET, with one a POST, as JSON when it looks like JSON. The page hears back through
     * vmlFromPhone("fetch:" + id, what came back, "") or (what came back or "", what went wrong).
     */
    @JavascriptInterface
    public void fetch(final String id, final String url, final String body) {
        new Thread(() -> {
            String answer = "", problem = "";
            java.net.HttpURLConnection c = null;
            try {
                if (url == null || !url.matches("(?i)https?://.+")) {
                    throw new IOException("Only http:// and https:// addresses can be fetched.");
                }
                c = (java.net.HttpURLConnection) new java.net.URL(url).openConnection();
                c.setConnectTimeout(15000);
                c.setReadTimeout(30000);
                c.setRequestProperty("User-Agent", "Visualised");
                if (body != null && !body.isEmpty()) {
                    c.setRequestMethod("POST");
                    c.setDoOutput(true);
                    String t = body.trim();
                    c.setRequestProperty("Content-Type", t.startsWith("{") || t.startsWith("[") ? "application/json" : "text/plain; charset=utf-8");
                    try (OutputStream out = c.getOutputStream()) {
                        out.write(body.getBytes(StandardCharsets.UTF_8));
                    }
                }
                int code = c.getResponseCode();
                java.io.InputStream in = code >= 400 ? c.getErrorStream() : c.getInputStream();
                if (in != null) {
                    try (java.io.InputStream src = in; java.io.ByteArrayOutputStream got = new java.io.ByteArrayOutputStream()) {
                        byte[] buf = new byte[8192];
                        for (int n; (n = src.read(buf)) > 0; ) {
                            if (got.size() + n > 2 * 1024 * 1024) {
                                throw new IOException("The answer was over 2 MB.");
                            }
                            got.write(buf, 0, n);
                        }
                        answer = got.toString("UTF-8");
                    }
                }
                if (code >= 400) {
                    problem = "The server said " + code + ".";
                }
            } catch (IOException | RuntimeException e) {
                problem = e.getMessage() == null ? "It couldn't be reached." : e.getMessage();
            } finally {
                if (c != null) {
                    c.disconnect();
                }
            }
            activity.tell("fetch:" + id, answer, problem);
        }).start();
    }

    /** Send a text message (an app exported on its own only). See Texts.send. */
    @JavascriptInterface
    public void smsSend(String id, String number, String text) {
        texts.send(id, number, text);
    }

    /** Hear texts as they arrive, or stop (an app exported on its own only). See Texts.watch. */
    @JavascriptInterface
    public void smsWatch(boolean on) {
        texts.watch(on);
    }

    /**
     * Hear push messages sent to this phone through Firebase, with the app's Firebase values as JSON; "" stops.
     * Only in an app exported on its own whose scripts use OnPush (the push template). See Push.
     */
    @JavascriptInterface
    public void pushWatch(String options) {
        if (options != null && !options.isEmpty() && !activity.isOwnApp()) {
            activity.tell("push", "", "Pushes can only reach an app exported on its own (vml apk).");
            return;
        }
        activity.runOnUiThread(() -> Push.watch(activity, options));
    }

    /** JSON: what is running the page. */
    @JavascriptInterface
    public String info() {
        JSONObject o = new JSONObject();
        try {
            o.put("platform", "android-app");
            o.put("app", true);
            o.put("version", activity.getPackageManager().getPackageInfo(activity.getPackageName(), 0).versionName);
            o.put("android", Build.VERSION.RELEASE);
            o.put("model", Build.MANUFACTURER + " " + Build.MODEL);
            BatteryManager battery = activity.getSystemService(BatteryManager.class);
            if (battery != null) {
                o.put("battery", battery.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY));
                o.put("charging", battery.isCharging());
            }
            ConnectivityManager net = activity.getSystemService(ConnectivityManager.class);
            o.put("online", net != null && net.getActiveNetwork() != null);
        } catch (JSONException | PackageManager.NameNotFoundException | RuntimeException ignored) {
            // what is there so far is still true
        }
        return o.toString();
    }

    /** Hand some text to another app: messages, email, notes, whatever the user picks. */
    @JavascriptInterface
    public void share(String text, String title) {
        Intent send = new Intent(Intent.ACTION_SEND);
        send.setType("text/plain");
        send.putExtra(Intent.EXTRA_TEXT, text == null ? "" : text);
        if (title != null && !title.isEmpty()) {
            send.putExtra(Intent.EXTRA_SUBJECT, title);
        }
        activity.runOnUiThread(() -> activity.startActivity(Intent.createChooser(send, title == null || title.isEmpty() ? null : title)));
    }

    /** A notification in the phone's own list. The first one asks the user's permission (Android 13 and later). */
    @JavascriptInterface
    public void notify(String title, String text) {
        activity.runOnUiThread(() -> activity.withPermission(
                Build.VERSION.SDK_INT >= 33 ? new String[]{"android.permission.POST_NOTIFICATIONS"} : new String[0],
                granted -> {
                    if (granted) {
                        post(title, text);
                    } else {
                        Toast.makeText(activity, (title == null ? "" : title + ": ") + (text == null ? "" : text), Toast.LENGTH_LONG).show();
                    }
                }));
    }

    private void post(String title, String text) {
        NotificationManager manager = activity.getSystemService(NotificationManager.class);
        if (manager == null) {
            return;
        }
        if (manager.getNotificationChannel(CHANNEL) == null) {
            manager.createNotificationChannel(new NotificationChannel(CHANNEL, "From your apps", NotificationManager.IMPORTANCE_DEFAULT));
        }
        Intent open = new Intent(activity, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent tap = PendingIntent.getActivity(activity, 0, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification note = new Notification.Builder(activity, CHANNEL)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle(title == null ? "" : title)
                .setContentText(text == null ? "" : text)
                .setStyle(new Notification.BigTextStyle().bigText(text == null ? "" : text))
                .setContentIntent(tap)
                .setAutoCancel(true)
                .build();
        manager.notify(nextNote++, note);
    }

    /** A line for whoever made the app: kept while the app runs, and shown from the list of apps (press and hold). */
    @JavascriptInterface
    public void log(String text) {
        activity.log(text == null ? "" : text);
    }

    /** What a QR code in a picture says, or "" if there is none to be read. The picture is its brightness alone:
     *  one byte for each dot, row by row, as base64. (The web view has no reader of its own that can be counted on.) */
    @JavascriptInterface
    public String readCode(String grey, int width, int height) {
        try {
            byte[] dots = android.util.Base64.decode(grey == null ? "" : grey, android.util.Base64.DEFAULT);
            if (width < 21 || height < 21 || dots.length < width * height) {
                return "";
            }
            com.google.zxing.LuminanceSource picture =
                    new com.google.zxing.PlanarYUVLuminanceSource(dots, width, height, 0, 0, width, height, false);
            java.util.Map<com.google.zxing.DecodeHintType, Object> hints = new java.util.EnumMap<>(com.google.zxing.DecodeHintType.class);
            hints.put(com.google.zxing.DecodeHintType.TRY_HARDER, Boolean.TRUE);
            return new com.google.zxing.qrcode.QRCodeReader()
                    .decode(new com.google.zxing.BinaryBitmap(new com.google.zxing.common.HybridBinarizer(picture)), hints).getText();
        } catch (com.google.zxing.ReaderException | RuntimeException e) {
            return "";                              // no code in this picture: the next one may have it
        }
    }

    /** A few words at the foot of the screen that go away by themselves. */
    @JavascriptInterface
    public void toast(String text) {
        activity.runOnUiThread(() -> Toast.makeText(activity, text == null ? "" : text, Toast.LENGTH_SHORT).show());
    }

    @JavascriptInterface
    public void vibrate(int milliseconds) {
        Vibrator v = activity.getSystemService(Vibrator.class);
        if (v != null && v.hasVibrator()) {
            v.vibrate(VibrationEffect.createOneShot(Math.max(1, Math.min(milliseconds, 5000)), VibrationEffect.DEFAULT_AMPLITUDE));
        }
    }

    /** Open a link in whatever on the phone handles it: a web page, tel:, sms:, mailto:, geo: (a map). */
    @JavascriptInterface
    public void open(String url) {
        final Uri u = Uri.parse(url == null ? "" : url);
        String scheme = u.getScheme() == null ? "" : u.getScheme().toLowerCase();
        if (!Arrays.asList("http", "https", "tel", "sms", "smsto", "mailto", "geo").contains(scheme)) {
            return;
        }
        activity.runOnUiThread(() -> {
            try {
                activity.startActivity(new Intent(Intent.ACTION_VIEW, u));
            } catch (ActivityNotFoundException e) {
                Toast.makeText(activity, "Nothing on this phone opens that.", Toast.LENGTH_SHORT).show();
            }
        });
    }

    /**
     * Give the user a file, in Downloads/Visualised. content is the text to put in it, or a data: address
     * (as a photo in an Image has) for a picture or anything else that isn't text. Returns the name, "" if it failed.
     */
    @JavascriptInterface
    public String saveFile(String name, String content) {
        String safe = (name == null ? "" : name).replaceAll("[\\\\/:*?\"<>|\\x00-\\x1f]", "_").trim();
        if (safe.isEmpty()) {
            safe = "file.txt";
        }
        byte[] data;
        String type = URLConnection.guessContentTypeFromName(safe);
        String text = content == null ? "" : content;
        int comma = text.indexOf(',');
        try {
            if (text.startsWith("data:") && comma > 0 && text.substring(0, comma).endsWith(";base64")) {
                data = Base64.decode(text.substring(comma + 1), Base64.DEFAULT);
                type = text.substring(5, comma - 7).isEmpty() ? type : text.substring(5, comma - 7);
            } else {
                data = text.getBytes(StandardCharsets.UTF_8);
            }
            ContentValues about = new ContentValues();
            about.put(MediaStore.Downloads.DISPLAY_NAME, safe);
            about.put(MediaStore.Downloads.MIME_TYPE, type == null ? "application/octet-stream" : type);
            about.put(MediaStore.Downloads.RELATIVE_PATH, "Download/Visualised");
            Uri where = activity.getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, about);
            if (where == null) {
                return "";
            }
            try (OutputStream out = activity.getContentResolver().openOutputStream(where)) {
                if (out == null) {
                    return "";
                }
                out.write(data);
            }
        } catch (IOException | RuntimeException e) {
            return "";
        }
        final String saved = safe;
        activity.runOnUiThread(() -> Toast.makeText(activity, saved + " is in Downloads, in Visualised.", Toast.LENGTH_LONG).show());
        return safe;
    }

    /** Say some text out loud. */
    @JavascriptInterface
    public void speak(final String text) {
        activity.runOnUiThread(() -> {
            if (voice == null) {
                voice = new TextToSpeech(activity, status -> {
                    voiceReady = status == TextToSpeech.SUCCESS;
                    if (voiceReady && waitingToSay != null) {
                        voice.speak(waitingToSay, TextToSpeech.QUEUE_ADD, null, "say");
                    }
                    waitingToSay = null;
                });
                waitingToSay = text;
            } else if (voiceReady) {
                voice.speak(text == null ? "" : text, TextToSpeech.QUEUE_ADD, null, "say");
            } else {
                waitingToSay = text;
            }
        });
    }

    /** How bright the screen is while this app is in front, 0 to 100. Anything below 0 hands it back to the phone. */
    @JavascriptInterface
    public void brightness(int percent) {
        activity.runOnUiThread(() -> {
            WindowManager.LayoutParams look = activity.getWindow().getAttributes();
            look.screenBrightness = percent < 0 ? WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE : Math.max(0.01f, Math.min(100, percent) / 100f);
            activity.getWindow().setAttributes(look);
        });
    }

    /** The torch (the camera's light), on or off. */
    @JavascriptInterface
    public void torch(boolean on) {
        CameraManager cameras = activity.getSystemService(CameraManager.class);
        if (cameras == null) {
            return;
        }
        try {
            for (String id : cameras.getCameraIdList()) {
                CameraCharacteristics c = cameras.getCameraCharacteristics(id);
                Integer facing = c.get(CameraCharacteristics.LENS_FACING);
                if (Boolean.TRUE.equals(c.get(CameraCharacteristics.FLASH_INFO_AVAILABLE))
                        && facing != null && facing == CameraCharacteristics.LENS_FACING_BACK) {
                    cameras.setTorchMode(id, on);
                    torchOn = on;
                    return;
                }
            }
        } catch (CameraAccessException | RuntimeException ignored) {
            // no torch, or the camera is busy
        }
    }

    /**
     * The Bluetooth devices this phone is paired with, as JSON. Asks the user's leave first; the page hears back
     * through vmlFromPhone("bluetooth", json, problem).
     */
    @JavascriptInterface
    public void bluetoothDevices() {
        activity.runOnUiThread(() -> activity.withPermission(
                Build.VERSION.SDK_INT >= 31 ? new String[]{"android.permission.BLUETOOTH_CONNECT"} : new String[0],
                granted -> activity.tell("bluetooth", granted ? Places.paired(activity) : "[]", granted ? "" : "Seeing Bluetooth devices wasn't allowed.")));
    }

    /**
     * Start (or stop) noting where the phone is when a paired device connects and goes away. To note a place
     * while the phone is in a pocket Android needs location allowed all the time, which only the user can
     * switch on, in the phone's settings: this takes them there. The page hears back through
     * vmlFromPhone("watching", state, problem): state is "watching", "stopped", or "partly" (it will note the
     * time a device went, but not the place).
     */
    @JavascriptInterface
    public void bluetoothWatch(final String address, final boolean on) {
        activity.runOnUiThread(() -> activity.watchBluetooth(address, on));
    }

    /** What has been noted, newest first, as JSON: device, name, what, time, and where when it could be found. */
    @JavascriptInterface
    public String bluetoothLog() {
        return Places.log(activity);
    }

    /** The air pressure in hectopascals, or "" on a phone with no barometer (or before its first reading). */
    @JavascriptInterface
    public String pressure() {
        if (air == null) {
            SensorManager sensors = activity.getSystemService(SensorManager.class);
            Sensor barometer = sensors == null ? null : sensors.getDefaultSensor(Sensor.TYPE_PRESSURE);
            if (barometer == null) {
                return "";
            }
            air = new SensorEventListener() {
                @Override
                public void onSensorChanged(SensorEvent e) {
                    pressureNow = e.values[0];
                }

                @Override
                public void onAccuracyChanged(Sensor sensor, int accuracy) {
                }
            };
            sensors.registerListener(air, barometer, SensorManager.SENSOR_DELAY_NORMAL);
        }
        return pressureNow > 0 ? String.valueOf(Math.round(pressureNow * 100) / 100.0) : "";
    }

    /** Hear what the user says. The words come back to the page later, through window.vmlFromPhone("listen", words, problem). */
    @JavascriptInterface
    public void listen(final String prompt) {
        activity.runOnUiThread(() -> activity.listen(prompt));
    }

    /**
     * Signal with the torch: pattern is milliseconds on, off, on, off... with commas between. Runs to its own
     * clock, off the page's, so the timing holds. The page is told when it is done: vmlFromPhone("flash").
     * An empty pattern stops one that is running.
     */
    @JavascriptInterface
    public void flash(String pattern) {
        final Thread before = signalling;
        if (before != null) {
            before.interrupt();
        }
        final java.util.List<Long> steps = new java.util.ArrayList<>();
        for (String part : (pattern == null ? "" : pattern).split(",")) {
            try {
                steps.add(Math.max(0, Math.min(Long.parseLong(part.trim()), 60000)));
            } catch (NumberFormatException ignored) {
                // not a number: left out
            }
        }
        if (steps.isEmpty()) {
            return;
        }
        Thread t = new Thread(() -> {
            boolean finished = false;
            try {
                if (before != null) {
                    before.join(500);
                }
                long due = SystemClock.uptimeMillis();
                for (int i = 0; i < steps.size(); i++) {
                    torch(i % 2 == 0);
                    due += steps.get(i);                // each change is timed from the start, so small delays don't add up
                    long wait = due - SystemClock.uptimeMillis();
                    if (wait > 0) {
                        Thread.sleep(wait);
                    }
                }
                finished = true;
            } catch (InterruptedException stopped) {
                // told to stop
            } finally {
                torch(false);
                if (finished) {
                    activity.tell("flash", "", "");
                }
            }
        }, "visualised-flash");
        signalling = t;
        t.start();
    }

    /** Get the voice ready, so the first thing an app says isn't kept waiting. */
    void warmVoice() {
        if (voice == null) {
            voice = new TextToSpeech(activity, status -> {
                voiceReady = status == TextToSpeech.SUCCESS;
                if (voiceReady && waitingToSay != null) {
                    voice.speak(waitingToSay, TextToSpeech.QUEUE_ADD, null, "say");
                }
                waitingToSay = null;
            });
        }
    }

    /** Keep the app going while the phone is used for something else. A notice in the phone's list says it is. */
    @JavascriptInterface
    public void background(boolean on) {
        activity.runOnUiThread(() -> activity.runInBackground(on));
    }

    /** The app on screen has been left: put back whatever it switched on. */
    void reset() {
        texts.stop();
        Push.stop();
        if (air != null) {
            SensorManager sensors = activity.getSystemService(SensorManager.class);
            if (sensors != null) {
                sensors.unregisterListener(air);
            }
            air = null;
            pressureNow = 0;
        }
        Thread running = signalling;
        if (running != null) {
            running.interrupt();
        }
        if (torchOn) {
            torch(false);
        }
        if (voice != null) {
            voice.stop();
        }
        brightness(-1);
    }

    void close() {
        reset();
        if (voice != null) {
            voice.shutdown();
            voice = null;
        }
    }

    /** Keep the screen on while this app is in front (a timer, a recipe, a checklist on site). */
    @JavascriptInterface
    public void keepAwake(boolean on) {
        activity.runOnUiThread(() -> {
            if (on) {
                activity.getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            } else {
                activity.getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            }
        });
    }
}
