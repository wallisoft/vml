package io.visualised.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.ActivityNotFoundException;
import android.content.ContentValues;
import android.content.Intent;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraManager;
import android.net.ConnectivityManager;
import android.net.Uri;
import android.os.BatteryManager;
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

    Device(MainActivity activity) {
        this.activity = activity;
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

    /** Keep the app going while the phone is used for something else. A notice in the phone's list says it is. */
    @JavascriptInterface
    public void background(boolean on) {
        activity.runOnUiThread(() -> activity.runInBackground(on));
    }

    /** The app on screen has been left: put back whatever it switched on. */
    void reset() {
        if (torchOn) {
            torch(false);
        }
        if (voice != null) {
            voice.stop();
        }
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
