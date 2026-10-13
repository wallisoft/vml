package io.visualised.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.provider.Telephony;
import android.telephony.SmsMessage;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Texts as they arrive, whether or not the app is open: Android wakes this for every text (the manifest asks it to,
 * in an app whose scripts use OnSms; vml/apk.py leaves it out of any other). Parts of a long text are put back
 * together, and each goes to the Inbox, which hands it to the page or keeps it until the page listens.
 */
public class Arriving extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (!Telephony.Sms.Intents.SMS_RECEIVED_ACTION.equals(intent.getAction())) {
            return;
        }
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
            Inbox.arrived(context, "sms", t.getKey(), t.getValue().toString());
        }
    }
}
