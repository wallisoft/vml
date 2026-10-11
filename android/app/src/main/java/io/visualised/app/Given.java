package io.visualised.app;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;

import java.io.File;
import java.io.FileNotFoundException;
import java.util.List;

/**
 * What this phone hands to another when the user sends an app to a friend: the app's page, and Visualised itself
 * for a friend who hasn't got it. Nothing can read these unless the user has just chosen to send them: each send
 * lends the one app it was given to (Quick Share, usually) a look at exactly those files.
 *
 *   content://io.visualised.app.given/app/<id>/<Name>.html   an app kept on this phone
 *   content://io.visualised.app.given/visualised/Visualised.apk
 */
public final class Given extends ContentProvider {
    static String AUTHORITY = "io.visualised.app.given";        // (an app exported on its own has its own name, and so its own: set as it starts)

    static Uri app(Apps.Kept app) {
        String name = app.name.replaceAll("[\\\\/:*?\"<>|\\p{Cntrl}]", " ").trim();
        return new Uri.Builder().scheme("content").authority(AUTHORITY).appendPath("app").appendPath(app.id)
                .appendPath((name.isEmpty() ? "App" : name) + ".html").build();
    }

    static Uri visualised() {
        return new Uri.Builder().scheme("content").authority(AUTHORITY).appendPath("visualised").appendPath("Visualised.apk").build();
    }

    private File file(Uri uri) throws FileNotFoundException {
        List<String> parts = uri.getPathSegments();
        File f = null;
        if (getContext() != null && parts.size() == 3 && "app".equals(parts.get(0))) {
            f = new Apps(getContext()).page(parts.get(1));
        } else if (getContext() != null && parts.size() == 2 && "visualised".equals(parts.get(0))) {
            f = new File(getContext().getApplicationInfo().sourceDir);
        }
        if (f == null || !f.isFile()) {
            throw new FileNotFoundException("Nothing is given at " + uri);
        }
        return f;
    }

    @Override
    public boolean onCreate() {
        AUTHORITY = getContext().getPackageName() + ".given";
        return true;
    }

    @Override
    public String getType(Uri uri) {
        String last = uri.getLastPathSegment();
        return last != null && last.endsWith(".apk") ? "application/vnd.android.package-archive" : "text/html";
    }

    @Override
    public Cursor query(Uri uri, String[] columns, String selection, String[] args, String order) {
        if (columns == null) {
            columns = new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE};
        }
        MatrixCursor answer = new MatrixCursor(columns, 1);
        try {
            File f = file(uri);
            Object[] row = new Object[columns.length];
            for (int i = 0; i < columns.length; i++) {
                if (OpenableColumns.DISPLAY_NAME.equals(columns[i])) {
                    row[i] = uri.getLastPathSegment();
                } else if (OpenableColumns.SIZE.equals(columns[i])) {
                    row[i] = f.length();
                }
            }
            answer.addRow(row);
        } catch (FileNotFoundException gone) {
            // an empty answer says so
        }
        return answer;
    }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (!"r".equals(mode)) {
            throw new FileNotFoundException("These can only be read.");
        }
        return ParcelFileDescriptor.open(file(uri), ParcelFileDescriptor.MODE_READ_ONLY);
    }

    @Override
    public Uri insert(Uri uri, ContentValues values) {
        return null;
    }

    @Override
    public int delete(Uri uri, String selection, String[] args) {
        return 0;
    }

    @Override
    public int update(Uri uri, ContentValues values, String selection, String[] args) {
        return 0;
    }
}
