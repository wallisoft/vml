package io.visualised.app;

import android.app.Application;

/** Starts Firebase (from the values the app's script gave) whenever the app's process starts, so that a push
 *  arriving with the app closed can be received. In the push template only. */
public class PushApp extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        Push.start(this);
    }
}
