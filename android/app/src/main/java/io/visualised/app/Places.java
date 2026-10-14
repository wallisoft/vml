package io.visualised.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.location.Location;
import android.location.LocationManager;
import android.os.Build;
import android.os.CancellationSignal;
import android.os.Handler;
import android.os.Looper;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Set;

/**
 * Notices a Bluetooth device the user chose (their car, say) connecting and going away, and writes down where
 * the phone was when it did: the one moment nobody remembers to press a button. Android wakes this for the
 * moment it happens, even when Visualised isn't running; an app reads the notes later (Device.bluetoothLog).
 *
 * Nothing is noted for a device the user hasn't chosen, the notes never leave the phone, and only the last
 * five hundred are kept (a desk keyboard comes and goes many times a day; an app that counts time with things,
 * like Clever Clogs, copies them into its own history whenever it runs).
 */
public class Places extends BroadcastReceiver {
    private static final String CHANNEL = "places";
    private static final int KEEP = 500;

    static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences("bluetooth", Context.MODE_PRIVATE);
    }

    static Set<String> chosen(Context c) {
        return new HashSet<>(prefs(c).getStringSet("devices", new HashSet<String>()));
    }

    static void choose(Context c, String address, boolean on) {
        Set<String> now = chosen(c);
        if (on) {
            now.add(address);
        } else {
            now.remove(address);
        }
        prefs(c).edit().putStringSet("devices", now).apply();
    }

    static boolean allowed(Context c, String permission) {
        return c.checkSelfPermission(permission) == PackageManager.PERMISSION_GRANTED;
    }

    /** May this app see the phone's Bluetooth devices? (Before Android 12 no asking was needed.) */
    static boolean bluetoothAllowed(Context c) {
        return Build.VERSION.SDK_INT < 31 || allowed(c, "android.permission.BLUETOOTH_CONNECT");
    }

    /** The devices the phone has been paired with, as JSON: name, address, and whether it is being watched. */
    @SuppressWarnings("MissingPermission")
    static String paired(Context c) {
        JSONArray out = new JSONArray();
        BluetoothManager manager = c.getSystemService(BluetoothManager.class);
        BluetoothAdapter adapter = manager == null ? null : manager.getAdapter();
        if (adapter == null || !bluetoothAllowed(c)) {
            return out.toString();
        }
        Set<String> watched = chosen(c);
        try {
            for (BluetoothDevice d : adapter.getBondedDevices()) {
                JSONObject o = new JSONObject();
                o.put("name", d.getName() == null ? d.getAddress() : d.getName());
                o.put("address", d.getAddress());
                o.put("watched", watched.contains(d.getAddress()));
                out.put(o);
            }
        } catch (JSONException | RuntimeException ignored) {
            // what was gathered so far
        }
        return out.toString();
    }

    private static File file(Context c) {
        return new File(c.getFilesDir(), "bluetooth-log.json");
    }

    static synchronized String log(Context c) {
        try (FileInputStream in = new FileInputStream(file(c))) {
            return new String(Apps.readAll(in, 1 << 20), StandardCharsets.UTF_8);
        } catch (IOException e) {
            return "[]";
        }
    }

    private static synchronized void note(Context c, JSONObject entry) {
        try {
            JSONArray old = new JSONArray(log(c)), now = new JSONArray();
            now.put(entry);                              // newest first
            for (int i = 0; i < old.length() && now.length() < KEEP; i++) {
                now.put(old.get(i));
            }
            try (FileOutputStream out = new FileOutputStream(file(c))) {
                out.write(now.toString().getBytes(StandardCharsets.UTF_8));
            }
        } catch (JSONException | IOException ignored) {
            // a note not written is a pity, never a crash
        }
    }

    @Override
    @SuppressWarnings("MissingPermission")
    public void onReceive(final Context context, Intent intent) {
        final boolean gone = BluetoothDevice.ACTION_ACL_DISCONNECTED.equals(intent.getAction());
        if (!gone && !BluetoothDevice.ACTION_ACL_CONNECTED.equals(intent.getAction())) {
            return;
        }
        BluetoothDevice device = Build.VERSION.SDK_INT >= 33
                ? intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE, BluetoothDevice.class)
                : intent.<BluetoothDevice>getParcelableExtra(BluetoothDevice.EXTRA_DEVICE);
        if (device == null || !chosen(context).contains(device.getAddress())) {
            return;                                      // not one the user asked about: nothing is noted
        }
        String called = device.getAddress();
        try {
            if (bluetoothAllowed(context) && device.getName() != null) {
                called = device.getName();
            }
        } catch (RuntimeException ignored) {
            // the address will do
        }
        final JSONObject entry = new JSONObject();
        try {
            entry.put("device", device.getAddress());
            entry.put("name", called);
            entry.put("what", gone ? "disconnected" : "connected");
            entry.put("time", System.currentTimeMillis() / 1000);
        } catch (JSONException ignored) {
            return;
        }
        if (!gone) {
            note(context, entry);
            return;
        }
        // Where was that? Android gives a receiver a short while to find out, so: the best fix it already has,
        // bettered by a fresh one if that arrives in time, and the air pressure (which tells one floor from another).
        final PendingResult pending = goAsync();
        final Handler main = new Handler(Looper.getMainLooper());
        final String name = called;
        final boolean[] done = {false};
        final Location[] best = {null};
        final float[] pressure = {0};
        final CancellationSignal stop = new CancellationSignal();
        final SensorManager sensors = context.getSystemService(SensorManager.class);
        final Sensor barometer = sensors == null ? null : sensors.getDefaultSensor(Sensor.TYPE_PRESSURE);
        final SensorEventListener air = new SensorEventListener() {
            @Override
            public void onSensorChanged(SensorEvent e) {
                pressure[0] = e.values[0];
            }

            @Override
            public void onAccuracyChanged(Sensor s, int accuracy) {
            }
        };
        final Runnable finish = () -> {
            if (done[0]) {
                return;
            }
            done[0] = true;
            stop.cancel();
            if (barometer != null) {
                sensors.unregisterListener(air);
            }
            try {
                if (best[0] != null) {
                    entry.put("latitude", best[0].getLatitude());
                    entry.put("longitude", best[0].getLongitude());
                    entry.put("accuracy", Math.round(best[0].getAccuracy()));
                    entry.put("fixed", best[0].getTime() / 1000);
                }
                if (pressure[0] > 0) {
                    entry.put("pressure", Math.round(pressure[0] * 100) / 100.0);
                }
            } catch (JSONException ignored) {
                // noted without them
            }
            note(context, entry);
            tell(context, name, best[0] != null);
            pending.finish();
        };
        if (barometer != null) {
            sensors.registerListener(air, barometer, SensorManager.SENSOR_DELAY_NORMAL);
        }
        boolean fine = allowed(context, "android.permission.ACCESS_FINE_LOCATION");
        boolean any = fine || allowed(context, "android.permission.ACCESS_COARSE_LOCATION");
        LocationManager where = context.getSystemService(LocationManager.class);
        if (any && where != null) {
            try {
                for (String provider : where.getProviders(true)) {
                    Location l = where.getLastKnownLocation(provider);
                    if (l != null && System.currentTimeMillis() - l.getTime() < 10 * 60 * 1000
                            && (best[0] == null || l.getAccuracy() < best[0].getAccuracy())) {
                        best[0] = l;
                    }
                }
                String provider = fine && where.isProviderEnabled(LocationManager.GPS_PROVIDER) ? LocationManager.GPS_PROVIDER
                        : where.isProviderEnabled(LocationManager.NETWORK_PROVIDER) ? LocationManager.NETWORK_PROVIDER : null;
                if (provider != null && Build.VERSION.SDK_INT >= 30) {
                    where.getCurrentLocation(provider, stop, context.getMainExecutor(), l -> {
                        if (l != null) {
                            best[0] = l;
                        }
                        finish.run();
                    });
                } else if (provider != null) {
                    where.requestSingleUpdate(provider, l -> {
                        best[0] = l;
                        finish.run();
                    }, Looper.getMainLooper());
                }
            } catch (RuntimeException notAllowedAfterAll) {
                // whatever was found before it stopped
            }
        }
        main.postDelayed(finish, 8000);                  // well inside what Android allows a receiver
    }

    /** A quiet notice that the place was noted (or couldn't be), so the user learns to trust it. */
    private static void tell(Context c, String name, boolean found) {
        if (Build.VERSION.SDK_INT >= 33 && !allowed(c, "android.permission.POST_NOTIFICATIONS")) {
            return;
        }
        NotificationManager manager = c.getSystemService(NotificationManager.class);
        if (manager == null) {
            return;
        }
        if (manager.getNotificationChannel(CHANNEL) == null) {
            manager.createNotificationChannel(new NotificationChannel(CHANNEL, "Places noted", NotificationManager.IMPORTANCE_LOW));
        }
        Intent open = new Intent(c, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        Notification n = new Notification.Builder(c, CHANNEL)
                .setSmallIcon(android.R.drawable.ic_menu_mylocation)
                .setContentTitle(found ? "Noted where you left " + name : "You left " + name)
                .setContentText(found ? "Open your app to be taken back to it." : "The phone couldn't tell where: location needs to be allowed all the time.")
                .setContentIntent(PendingIntent.getActivity(c, 2, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT))
                .setAutoCancel(true)
                .build();
        manager.notify(9100, n);
    }
}
