package io.visualised.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/**
 * The phone has restarted. An app that was running in the background (RunInBackground) when it went down is opened
 * again where the phone allows it, and in any case a notice says it stopped and offers to start it with a tap.
 * Only an app whose scripts use RunInBackground carries this (vml/apk.py).
 */
public class Booted extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (!Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())
                || !context.getSharedPreferences("visualised", Context.MODE_PRIVATE).getBoolean("kept_running", false)) {
            return;
        }
        Intent open = new Intent(context, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            context.startActivity(open);                     // allowed on some phones; quietly refused on others
        } catch (RuntimeException ignored) {
            // the notice below is the way back
        }
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        if (manager == null) {
            return;
        }
        if (manager.getNotificationChannel("restarted") == null) {
            manager.createNotificationChannel(new NotificationChannel("restarted", "After a restart", NotificationManager.IMPORTANCE_HIGH));
        }
        String name = String.valueOf(context.getApplicationInfo().loadLabel(context.getPackageManager()));
        manager.notify(9003, new Notification.Builder(context, "restarted")
                .setSmallIcon(android.R.drawable.ic_media_play)
                .setContentTitle(name + " stopped when the phone restarted")
                .setContentText("Tap to start it again.")
                .setContentIntent(PendingIntent.getActivity(context, 3, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT))
                .setAutoCancel(true)
                .build());
    }
}
