package io.visualised.app;

import android.content.Context;
import android.content.SharedPreferences;

import com.google.firebase.FirebaseApp;
import com.google.firebase.FirebaseOptions;
import com.google.firebase.messaging.FirebaseMessaging;

import org.json.JSONException;
import org.json.JSONObject;

/**
 * Push messages through Firebase Cloud Messaging, for an app exported on its own whose scripts use OnPush.
 *
 * There is no google-services.json: the app's script hands over its Firebase project's four public values, as
 * JSON {"project", "app", "key", "sender"}. They are kept, so that a push arriving with the app closed can start
 * Firebase again (PushApp). Everything heard goes to the page as vmlFromPhone("push", kind, what):
 *   ("push", "token", the token)       this phone's address for pushes: the app gives it to its server
 *   ("push", "message", JSON)          a push's data, as the server sent it
 *   ("push", "", what went wrong)      it couldn't start
 * A push that arrives with no page listening (the app was closed) shows a notice instead, which opens the app.
 */
final class Push {
    static volatile boolean watching;
    private static final String KEPT = "push";

    private Push() {
    }

    static boolean carried() {
        return true;
    }

    private static SharedPreferences kept(Context c) {
        return c.getApplicationContext().getSharedPreferences(KEPT, Context.MODE_PRIVATE);
    }

    /** Start Firebase from the kept values, if it isn't going already. True if it is going. */
    static boolean start(Context c) {
        if (!FirebaseApp.getApps(c).isEmpty()) {
            return true;
        }
        SharedPreferences p = kept(c);
        if (p.getString("app", "").isEmpty()) {
            return false;
        }
        try {
            FirebaseApp.initializeApp(c.getApplicationContext(), new FirebaseOptions.Builder()
                    .setProjectId(p.getString("project", ""))
                    .setApplicationId(p.getString("app", ""))
                    .setApiKey(p.getString("key", ""))
                    .setGcmSenderId(p.getString("sender", ""))
                    .build());
            return true;
        } catch (RuntimeException e) {
            return false;
        }
    }

    /** Is the app expecting pushes (started with OnPush and not stopped)? Then a push with nobody listening gets a notice. */
    static boolean wanted(Context c) {
        return kept(c).getBoolean("on", false);
    }

    /** Hear pushes, with the app's Firebase values as JSON; "" stops hearing them (the phone keeps its token). */
    static void watch(final MainActivity activity, String options) {
        if (options == null || options.isEmpty()) {
            stop();
            kept(activity).edit().putBoolean("on", false).apply();
            return;
        }
        JSONObject o;
        try {
            o = new JSONObject(options);
        } catch (JSONException e) {
            activity.tell("push", "", "OnPush needs the Firebase values as JSON: project, app, key and sender.");
            return;
        }
        String app = o.optString("app"), project = o.optString("project"), key = o.optString("key"), sender = o.optString("sender");
        if (app.isEmpty() || project.isEmpty() || key.isEmpty() || sender.isEmpty()) {
            activity.tell("push", "", "OnPush needs all four Firebase values: project, app, key and sender.");
            return;
        }
        SharedPreferences p = kept(activity);
        boolean changed = !app.equals(p.getString("app", "")) && !p.getString("app", "").isEmpty();
        p.edit().putString("project", project).putString("app", app).putString("key", key).putString("sender", sender)
                .putBoolean("on", true).apply();
        if (changed && !FirebaseApp.getApps(activity).isEmpty()) {
            activity.tell("push", "", "The Firebase values changed: they take effect when the app is next started.");
        }
        if (!start(activity)) {
            activity.tell("push", "", "Firebase couldn't be started with those values.");
            return;
        }
        watching = true;
        activity.withPermission(android.os.Build.VERSION.SDK_INT >= 33
                ? new String[]{"android.permission.POST_NOTIFICATIONS"} : new String[0], granted -> { });
        FirebaseMessaging.getInstance().getToken().addOnCompleteListener(t -> {
            if (t.isSuccessful() && t.getResult() != null) {
                activity.tell("push", "token", t.getResult());
            } else {
                Exception e = t.getException();
                activity.tell("push", "", "This phone couldn't get a push token"
                        + (e != null && e.getMessage() != null ? ": " + e.getMessage() : ".")
                        + " (Is Google Play services on this phone, and up to date?)");
            }
        });
    }

    static void stop() {
        watching = false;
    }
}
