package io.visualised.app;

import android.app.Activity;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Build;
import android.provider.Telephony;
import android.telephony.SmsManager;
import android.telephony.SmsMessage;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Text messages (SMS), for an app exported on its own whose maker used SmsSend or OnSms: only then does its APK
 * carry the permissions, and only then does this do anything. Never for the apps opened inside Visualised itself,
 * which anyone could hand the user; a text can cost money, and texts that arrive are private.
 */
final class Texts {
    private static final String SENT = ".TEXT_SENT";
    private final MainActivity activity;
    private BroadcastReceiver arriving;

    Texts(MainActivity activity) {
        this.activity = activity;
    }

    private boolean allowed(String why) {
        if (activity.isOwnApp()) {
            return true;
        }
        activity.tell(why, "", "Texts can only be sent and read by an app exported on its own (vml apk).");
        return false;
    }

    /** Send a text; the page hears back through vmlFromPhone("sms-sent:" + id, "sent", "") or ("", what went wrong). */
    void send(final String id, final String number, final String text) {
        final String answer = "sms-sent:" + id;
        if (!allowed(answer)) {
            return;
        }
        if (number == null || number.replaceAll("[^0-9]", "").length() < 3 || text == null || text.isEmpty()) {
            activity.tell(answer, "", "A text needs a number and something to say.");
            return;
        }
        activity.runOnUiThread(() -> activity.withPermission(new String[]{"android.permission.SEND_SMS"}, granted -> {
            if (!granted) {
                activity.tell(answer, "", "Sending texts wasn't allowed.");
                return;
            }
            try {
                SmsManager sms = Build.VERSION.SDK_INT >= 31 ? activity.getSystemService(SmsManager.class) : SmsManager.getDefault();
                ArrayList<String> parts = sms.divideMessage(text);
                final String action = activity.getPackageName() + SENT + "." + id;
                final int[] left = {parts.size()};
                final String[] problem = {""};
                BroadcastReceiver result = new BroadcastReceiver() {
                    @Override
                    public void onReceive(Context context, Intent intent) {
                        if (getResultCode() != Activity.RESULT_OK && problem[0].isEmpty()) {
                            problem[0] = why(getResultCode());
                        }
                        if (--left[0] == 0) {
                            try {
                                activity.getApplicationContext().unregisterReceiver(this);
                            } catch (IllegalArgumentException ignored) {
                                // already gone
                            }
                            activity.tell(answer, problem[0].isEmpty() ? "sent" : "", problem[0]);
                        }
                    }
                };
                register(result, new IntentFilter(action), null, false);
                ArrayList<PendingIntent> sent = new ArrayList<>();
                for (int i = 0; i < parts.size(); i++) {
                    Intent done = new Intent(action).setPackage(activity.getPackageName());
                    sent.add(PendingIntent.getBroadcast(activity, (id + ":" + i).hashCode(), done, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_ONE_SHOT));
                }
                sms.sendMultipartTextMessage(number, null, parts, sent, null);
            } catch (RuntimeException e) {
                activity.tell(answer, "", "The text couldn't be sent: " + e.getMessage());
            }
        }));
    }

    private static String why(int code) {
        switch (code) {
            case SmsManager.RESULT_ERROR_NO_SERVICE:
                return "No signal.";
            case SmsManager.RESULT_ERROR_RADIO_OFF:
                return "The phone's radio is off (flight mode?).";
            case SmsManager.RESULT_ERROR_NULL_PDU:
                return "The phone couldn't make the text.";
            default:
                return "The network wouldn't take it (" + code + ").";
        }
    }

    /**
     * Hear texts as they arrive, or stop. Each comes to the page as vmlFromPhone("sms", from, text): parts of a
     * long text are put back together. A refusal comes as ("sms", "", what went wrong).
     */
    void watch(final boolean on) {
        if (!on) {
            stop();
            return;
        }
        if (!allowed("sms") || arriving != null) {
            return;
        }
        activity.runOnUiThread(() -> activity.withPermission(new String[]{"android.permission.RECEIVE_SMS"}, granted -> {
            if (!granted) {
                activity.tell("sms", "", "Reading texts as they arrive wasn't allowed.");
                return;
            }
            if (arriving != null) {
                return;
            }
            arriving = new BroadcastReceiver() {
                @Override
                public void onReceive(Context context, Intent intent) {
                    SmsMessage[] parts = Telephony.Sms.Intents.getMessagesFromIntent(intent);
                    if (parts == null) {
                        return;
                    }
                    Map<String, StringBuilder> texts = new LinkedHashMap<>();
                    for (SmsMessage part : parts) {
                        if (part == null || part.getOriginatingAddress() == null) {
                            continue;
                        }
                        StringBuilder text = texts.get(part.getOriginatingAddress());
                        if (text == null) {
                            text = new StringBuilder();
                            texts.put(part.getOriginatingAddress(), text);
                        }
                        if (part.getMessageBody() != null) {
                            text.append(part.getMessageBody());
                        }
                    }
                    for (Map.Entry<String, StringBuilder> t : texts.entrySet()) {
                        activity.tell("sms", t.getKey(), t.getValue().toString());
                    }
                }
            };
            // Only the phone itself (which holds BROADCAST_SMS) can hand us a text: no other app can fake one.
            register(arriving, new IntentFilter(Telephony.Sms.Intents.SMS_RECEIVED_ACTION), "android.permission.BROADCAST_SMS", true);
        }));
    }

    private void register(BroadcastReceiver receiver, IntentFilter filter, String from, boolean fromOutside) {
        Context app = activity.getApplicationContext();
        if (Build.VERSION.SDK_INT >= 33) {
            app.registerReceiver(receiver, filter, from, null, fromOutside ? Context.RECEIVER_EXPORTED : Context.RECEIVER_NOT_EXPORTED);
        } else {
            app.registerReceiver(receiver, filter, from, null);
        }
    }

    void stop() {
        if (arriving != null) {
            try {
                activity.getApplicationContext().unregisterReceiver(arriving);
            } catch (IllegalArgumentException ignored) {
                // already gone
            }
            arriving = null;
        }
    }
}
