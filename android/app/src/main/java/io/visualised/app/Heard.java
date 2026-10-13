package io.visualised.app;

import android.app.Notification;
import android.app.Person;
import android.net.Uri;
import android.os.Bundle;
import android.os.Parcelable;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

/**
 * Messages that arrive in the phone's messaging apps, read from their notices: this is how an RCS message (which
 * no app but Google Messages can read) still reaches an app that uses OnMessages. Only an app exported on its own
 * whose scripts use OnMessages carries this (vml/apk.py), and only once its user has turned on notification access
 * for it. It reads the messaging apps' notices and nothing else, and only passes on messages from other people:
 * never the phone owner's own replies.
 */
public class Heard extends NotificationListenerService {
    static final Set<String> APPS = new HashSet<>(Arrays.asList(
            "com.google.android.apps.messaging", "com.samsung.android.messaging"));

    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        if (sbn == null || !APPS.contains(sbn.getPackageName())) {
            return;
        }
        Notification n = sbn.getNotification();
        if (n == null || (n.flags & Notification.FLAG_GROUP_SUMMARY) != 0) {
            return;
        }
        Bundle x = n.extras;
        String from = null, text = null;
        Parcelable[] said = x.getParcelableArray(Notification.EXTRA_MESSAGES);
        if (said != null && said.length > 0 && said[said.length - 1] instanceof Bundle) {
            Bundle last = (Bundle) said[said.length - 1];     // the newest message in the conversation
            CharSequence t = last.getCharSequence("text");
            text = t == null ? null : t.toString();
            Person who = last.getParcelable("sender_person");
            CharSequence name = last.getCharSequence("sender");
            if (who == null && name == null) {
                return;                                   // the phone owner's own message: not passed on
            }
            from = number(who != null ? who.getUri() : null);
            if (from == null) {
                CharSequence n2 = who != null && who.getName() != null ? who.getName() : name;
                from = n2 == null ? null : n2.toString();
            }
        }
        if (text == null) {                               // an app that doesn't say it as a conversation
            CharSequence title = x.getCharSequence(Notification.EXTRA_TITLE);
            CharSequence body = x.getCharSequence(Notification.EXTRA_BIG_TEXT);
            if (body == null) {
                body = x.getCharSequence(Notification.EXTRA_TEXT);
            }
            from = title == null ? null : title.toString();
            text = body == null ? null : body.toString();
        }
        if (from == null || text == null) {
            return;
        }
        Inbox.arrived(this, "messages", from, text);
    }

    /** A person's tel: address as a number, or null. */
    private static String number(String uri) {
        if (uri == null || !uri.startsWith("tel:")) {
            return null;
        }
        String n = Uri.decode(uri.substring(4)).replaceAll("[^0-9+]", "");
        return n.isEmpty() ? null : n;
    }
}
