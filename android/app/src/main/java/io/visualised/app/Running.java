package io.visualised.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;

/**
 * Keeps Visualised alive while an app that asked to run in the background is not on screen. Android only lets
 * that happen with a notice in the phone's list saying so, which this shows; tapping it comes back to the app.
 */
public class Running extends Service {
    private static final String CHANNEL = "running";
    private PowerManager.WakeLock awake;

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String name = intent == null ? null : intent.getStringExtra("name");
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager != null && manager.getNotificationChannel(CHANNEL) == null) {
            manager.createNotificationChannel(new NotificationChannel(CHANNEL, "Apps running in the background", NotificationManager.IMPORTANCE_LOW));
        }
        Intent open = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
        Notification note = new Notification.Builder(this, CHANNEL)
                .setSmallIcon(android.R.drawable.ic_media_play)
                .setContentTitle((name == null || name.isEmpty() ? "An app" : name) + " is running")
                .setContentText("Tap to go back to it.")
                .setContentIntent(PendingIntent.getActivity(this, 1, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT))
                .setOngoing(true)
                .build();
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(9001, note, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        } else {
            startForeground(9001, note);
        }
        PowerManager power = getSystemService(PowerManager.class);
        if (awake == null && power != null) {
            awake = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "visualised:running");
            awake.acquire(6 * 60 * 60 * 1000L);         // never for ever: six hours, then the phone may sleep
        }
        return START_NOT_STICKY;
    }

    @Override
    public void onTaskRemoved(Intent rootIntent) {      // swiped away from the recent apps: stop
        stopSelf();
    }

    @Override
    public void onDestroy() {
        if (awake != null && awake.isHeld()) {
            awake.release();
        }
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
