package io.visualised.app;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayDeque;
import java.util.Iterator;

/**
 * Where texts and messages that arrive end up. If the app on screen is listening (OnSms, OnMessages) each goes
 * straight to it; if not (the app was closed, or hasn't started listening yet) it waits here, kept on the phone,
 * and goes to the app as soon as it listens. The same message heard twice (as a text, and again as the messaging
 * app's notice of it) is passed on once.
 */
final class Inbox {
    static volatile boolean texts, messages;           // is the page listening for each kind
    private static final ArrayDeque<String[]> recent = new ArrayDeque<>();   // {what was said, when}, for doubles
    private static final long SAME = 3 * 60 * 1000L;
    private static final int KEEP = 50;

    private Inbox() {
    }

    /** A text ("sms") or a messaging app's message ("messages") has arrived. */
    static synchronized void arrived(Context c, String kind, String from, String text) {
        if (text == null || text.trim().isEmpty() || seen(text)) {
            return;
        }
        MainActivity page = MainActivity.onScreen;
        boolean listening = "sms".equals(kind) ? texts : messages;
        if (page != null && listening) {
            page.tell(kind, from, text);
            return;
        }
        SharedPreferences p = kept(c);
        JSONArray waiting = waiting(p);
        try {
            waiting.put(new JSONObject().put("kind", kind).put("from", from).put("text", text).put("at", System.currentTimeMillis()));
        } catch (JSONException ignored) {
            return;
        }
        while (waiting.length() > KEEP) {
            waiting.remove(0);
        }
        p.edit().putString("waiting", waiting.toString()).apply();
    }

    /** The page has started listening for this kind: hand it everything that waited. */
    static synchronized void flush(MainActivity page, String kind) {
        SharedPreferences p = kept(page);
        JSONArray waiting = waiting(p), left = new JSONArray();
        for (int i = 0; i < waiting.length(); i++) {
            JSONObject m = waiting.optJSONObject(i);
            if (m == null) {
                continue;
            }
            if (kind.equals(m.optString("kind"))) {
                page.tell(kind, m.optString("from"), m.optString("text"));
            } else {
                left.put(m);
            }
        }
        p.edit().putString("waiting", left.toString()).apply();
    }

    /** Heard in the last few minutes already (by the other way in)? Remembers it if not. */
    private static boolean seen(String text) {
        long now = System.currentTimeMillis();
        String said = text.trim();
        for (Iterator<String[]> it = recent.iterator(); it.hasNext(); ) {
            String[] r = it.next();
            if (now - Long.parseLong(r[1]) > SAME) {
                it.remove();
            } else if (r[0].equals(said)) {
                return true;
            }
        }
        recent.add(new String[]{said, String.valueOf(now)});
        while (recent.size() > KEEP) {
            recent.removeFirst();
        }
        return false;
    }

    private static SharedPreferences kept(Context c) {
        return c.getApplicationContext().getSharedPreferences("inbox", Context.MODE_PRIVATE);
    }

    private static JSONArray waiting(SharedPreferences p) {
        try {
            return new JSONArray(p.getString("waiting", "[]"));
        } catch (JSONException e) {
            return new JSONArray();
        }
    }
}
