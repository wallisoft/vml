package io.visualised.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Intent;

import androidx.annotation.NonNull;

import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;

import org.json.JSONObject;

import java.util.Map;

/** Where Firebase hands over a push. To the page if one is listening; otherwise a notice that opens the app. */
public class PushService extends FirebaseMessagingService {
    private static final String CHANNEL = "pushes";

    @Override
    public void onMessageReceived(@NonNull RemoteMessage message) {
        JSONObject data = new JSONObject();
        try {
            for (Map.Entry<String, String> e : message.getData().entrySet()) {
                data.put(e.getKey(), e.getValue());
            }
        } catch (org.json.JSONException ignored) {
            // a key Firebase let through that JSON can't hold: left out
        }
        MainActivity page = MainActivity.onScreen;
        if (Push.watching && page != null) {
            page.tell("push", "message", data.toString());
            return;
        }
        if (Push.wanted(this)) {
            notice(data.optString("title"), data.optString("body"));
        }
    }

    @Override
    public void onNewToken(@NonNull String token) {
        MainActivity page = MainActivity.onScreen;
        if (Push.watching && page != null) {
            page.tell("push", "token", token);
        }
    }

    private void notice(String title, String body) {
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager == null) {
            return;
        }
        if (manager.getNotificationChannel(CHANNEL) == null) {
            manager.createNotificationChannel(new NotificationChannel(CHANNEL, "Messages for this app", NotificationManager.IMPORTANCE_DEFAULT));
        }
        String name = String.valueOf(getApplicationInfo().loadLabel(getPackageManager()));
        Intent open = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        manager.notify(9002, new Notification.Builder(this, CHANNEL)
                .setSmallIcon(android.R.drawable.stat_notify_chat)
                .setContentTitle(title.isEmpty() ? name : title)
                .setContentText(body.isEmpty() ? "Something is waiting: tap to open " + name + "." : body)
                .setContentIntent(PendingIntent.getActivity(this, 2, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT))
                .setAutoCancel(true)
                .build());
    }
}
