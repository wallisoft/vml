package io.visualised.app;

/**
 * Push messages (Firebase), in Visualised itself and in apps exported from the plain template: not carried here.
 * An app whose scripts use OnPush is exported from the push template instead (vml/apk.py), whose Push does the work.
 */
final class Push {
    private Push() {
    }

    static boolean carried() {
        return false;
    }

    static void watch(MainActivity activity, String options) {
        if (options != null && !options.isEmpty()) {
            activity.tell("push", "", "This app wasn't exported with push. Export it again: OnPush in its scripts picks the push template.");
        }
    }

    static void stop() {
        // nothing to stop
    }
}
