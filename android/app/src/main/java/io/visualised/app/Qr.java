package io.visualised.app;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/**
 * QR codes, made here: no library needed. Enough of the standard for an address or a line of text: bytes, error
 * correction M (about 15% of the picture can be lost), versions 1 to 10 (up to 213 characters). The same code,
 * dot for dot, as the designer makes (vml/qr.py): the two are checked against each other.
 */
final class Qr {
    private Qr() {
    }

    // {total codewords, error-correction codewords per block, blocks, data codewords in each, [more blocks, data in each]}
    private static final int[][] VERSIONS = {null, {26, 10, 1, 16}, {44, 16, 1, 28}, {70, 26, 1, 44}, {100, 18, 2, 32},
            {134, 24, 2, 43}, {172, 16, 4, 27}, {196, 18, 4, 31}, {242, 22, 2, 38, 2, 39}, {292, 22, 3, 36, 2, 37},
            {346, 26, 4, 43, 1, 44}};
    private static final int[][] ALIGN = {null, {}, {6, 18}, {6, 22}, {6, 26}, {6, 30}, {6, 34}, {6, 22, 38}, {6, 24, 42},
            {6, 26, 46}, {6, 28, 50}};
    private static final int[] EXP = new int[512], LOG = new int[256];

    static {
        int x = 1;
        for (int i = 0; i < 255; i++) {
            EXP[i] = x;
            LOG[x] = i;
            x <<= 1;
            if ((x & 0x100) != 0) {
                x ^= 0x11D;
            }
        }
        for (int i = 255; i < 512; i++) {
            EXP[i] = EXP[i - 255];
        }
    }

    private static int mul(int a, int b) {
        return a == 0 || b == 0 ? 0 : EXP[LOG[a] + LOG[b]];
    }

    /** The Reed-Solomon codewords that follow a block of data. */
    private static int[] ecc(int[] data, int count) {
        int[] gen = {1};
        for (int i = 0; i < count; i++) {
            int[] next = new int[gen.length + 1];
            for (int j = 0; j < gen.length; j++) {
                next[j] ^= gen[j];
                next[j + 1] ^= mul(gen[j], EXP[i]);
            }
            gen = next;
        }
        int[] rest = new int[data.length + count];
        System.arraycopy(data, 0, rest, 0, data.length);
        for (int i = 0; i < data.length; i++) {
            int lead = rest[i];
            if (lead != 0) {
                for (int j = 0; j < gen.length; j++) {
                    rest[i + j] ^= mul(gen[j], lead);
                }
            }
        }
        int[] out = new int[count];
        System.arraycopy(rest, data.length, out, 0, count);
        return out;
    }

    private static int capacity(int version) {
        int[] v = VERSIONS[version];
        int total = 0;
        for (int i = 2; i < v.length; i += 2) {
            total += v[i] * v[i + 1];
        }
        return total;
    }

    private static int[] codewords(byte[] raw, int version) {
        int[] v = VERSIONS[version];
        int ec = v[1], capacity = capacity(version);
        StringBuilder bits = new StringBuilder("0100");
        String count = Integer.toBinaryString(raw.length);
        for (int i = count.length(); i < (version >= 10 ? 16 : 8); i++) {
            bits.append('0');
        }
        bits.append(count);
        for (byte b : raw) {
            String s = Integer.toBinaryString(b & 0xFF);
            for (int i = s.length(); i < 8; i++) {
                bits.append('0');
            }
            bits.append(s);
        }
        for (int i = Math.min(4, capacity * 8 - bits.length()); i > 0; i--) {
            bits.append('0');
        }
        while (bits.length() % 8 != 0) {
            bits.append('0');
        }
        int[] data = new int[capacity];
        int have = bits.length() / 8;
        for (int i = 0; i < have; i++) {
            data[i] = Integer.parseInt(bits.substring(i * 8, i * 8 + 8), 2);
        }
        for (int i = have; i < capacity; i++) {
            data[i] = (i - have) % 2 == 0 ? 0xEC : 0x11;
        }
        List<int[]> blocks = new ArrayList<>(), checks = new ArrayList<>();
        int at = 0, longest = 0;
        for (int g = 2; g < v.length; g += 2) {
            for (int n = 0; n < v[g]; n++) {
                int[] block = new int[v[g + 1]];
                System.arraycopy(data, at, block, 0, block.length);
                at += block.length;
                blocks.add(block);
                checks.add(ecc(block, ec));
                longest = Math.max(longest, block.length);
            }
        }
        int[] out = new int[v[0]];
        int o = 0;
        for (int i = 0; i < longest; i++) {
            for (int[] b : blocks) {
                if (i < b.length) {
                    out[o++] = b[i];
                }
            }
        }
        for (int i = 0; i < ec; i++) {
            for (int[] c : checks) {
                out[o++] = c[i];
            }
        }
        return out;
    }

    /** The remainder that protects the format (and version) information. */
    private static int bch(int value, int poly, int bits) {
        int reg = value << bits;
        int top = 32 - Integer.numberOfLeadingZeros(poly);
        for (int shift = (32 - Integer.numberOfLeadingZeros(reg)) - top; shift >= 0; shift--) {
            if ((reg >> (shift + top - 1) & 1) != 0) {
                reg ^= poly << shift;
            }
        }
        return reg;
    }

    private static int count(String line, String what) {
        int n = 0;
        for (int i = line.indexOf(what); i >= 0; i = line.indexOf(what, i + what.length())) {
            n++;
        }
        return n;
    }

    private static int penalty(boolean[][] m) {
        int n = m.length, score = 0;
        for (int turn = 0; turn < 2; turn++) {          // rows, then columns: runs of five or more, and finder look-alikes
            for (int a = 0; a < n; a++) {
                int run = 0;
                Boolean last = null;
                StringBuilder line = new StringBuilder();
                for (int b = 0; b < n; b++) {
                    boolean cell = turn == 0 ? m[a][b] : m[b][a];
                    line.append(cell ? '1' : '0');
                    if (last != null && cell == last) {
                        run++;
                    } else {
                        if (run >= 5) {
                            score += run - 2;
                        }
                        run = 1;
                        last = cell;
                    }
                }
                if (run >= 5) {
                    score += run - 2;
                }
                score += 40 * (count(line.toString(), "10111010000") + count(line.toString(), "00001011101"));
            }
        }
        int dark = 0;
        for (int y = 0; y < n; y++) {
            for (int x = 0; x < n; x++) {
                if (m[y][x]) {
                    dark++;
                }
                if (y < n - 1 && x < n - 1 && m[y][x] == m[y][x + 1] && m[y][x] == m[y + 1][x] && m[y][x] == m[y + 1][x + 1]) {
                    score += 3;                         // 2 x 2 blocks of one colour
                }
            }
        }
        int percent = dark * 100 / (n * n);             // far from half dark
        return score + 10 * (Math.abs(percent - 50) / 5);
    }

    private static boolean mask(int which, int y, int x) {
        switch (which) {
            case 0: return (y + x) % 2 == 0;
            case 1: return y % 2 == 0;
            case 2: return x % 3 == 0;
            case 3: return (y + x) % 3 == 0;
            case 4: return (y / 2 + x / 3) % 2 == 0;
            case 5: return (y * x) % 2 + (y * x) % 3 == 0;
            case 6: return ((y * x) % 2 + (y * x) % 3) % 2 == 0;
            default: return ((y + x) % 2 + (y * x) % 3) % 2 == 0;
        }
    }

    /** The code for some text: rows of dark (true) and light. Null if it is too long (213 characters at most). */
    static boolean[][] matrix(String text) {
        byte[] raw = text.getBytes(StandardCharsets.UTF_8);
        int version = 0;
        for (int v = 1; v <= 10 && version == 0; v++) {
            if (raw.length <= capacity(v) - (v >= 10 ? 3 : 2)) {
                version = v;
            }
        }
        if (version == 0) {
            return null;
        }
        final int n = 17 + 4 * version;
        boolean[][] m = new boolean[n][n], fixed = new boolean[n][n];
        int[][] corners = {{0, 0}, {0, n - 7}, {n - 7, 0}};
        for (int[] c : corners) {                       // the three corner squares, with their margins
            for (int y = -1; y < 8; y++) {
                for (int x = -1; x < 8; x++) {
                    boolean inside = y >= 0 && y <= 6 && x >= 0 && x <= 6;
                    put(m, fixed, c[0] + y, c[1] + x, inside && (y == 0 || y == 6 || x == 0 || x == 6 || (y >= 2 && y <= 4 && x >= 2 && x <= 4)));
                }
            }
        }
        for (int cy : ALIGN[version]) {                 // the small squares that keep a big code straight
            for (int cx : ALIGN[version]) {
                if (fixed[cy][cx]) {
                    continue;
                }
                for (int y = -2; y < 3; y++) {
                    for (int x = -2; x < 3; x++) {
                        put(m, fixed, cy + y, cx + x, Math.max(Math.abs(y), Math.abs(x)) != 1);
                    }
                }
            }
        }
        for (int i = 8; i < n - 8; i++) {               // the dotted lines between the corners
            if (!fixed[6][i]) {
                put(m, fixed, 6, i, i % 2 == 0);
            }
            if (!fixed[i][6]) {
                put(m, fixed, i, 6, i % 2 == 0);
            }
        }
        put(m, fixed, n - 8, 8, true);
        for (int i = 0; i < 9; i++) {                   // room for the format information
            int[][] spots = {{8, i}, {i, 8}, {8, n - 1 - i}, {n - 1 - i, 8}};
            for (int[] s : spots) {
                if (i < 8 || (s[0] == 8 && s[1] == 8)) {
                    fixed[s[0]][s[1]] = true;
                }
            }
        }
        if (version >= 7) {
            int info = (version << 12) | bch(version, 0x1F25, 12);
            for (int i = 0; i < 18; i++) {
                boolean bit = (info >> i & 1) != 0;
                put(m, fixed, i / 3, n - 11 + i % 3, bit);
                put(m, fixed, n - 11 + i % 3, i / 3, bit);
            }
        }

        int[] words = codewords(raw, version);
        int total = words.length * 8, at = 0, x = n - 1;
        boolean up = true;
        List<int[]> cells = new ArrayList<>();
        while (x > 0) {                                 // the data, in two-wide columns from the right, snaking
            if (x == 6) {
                x--;
            }
            for (int step = 0; step < n; step++) {
                int y = up ? n - 1 - step : step;
                for (int xx = x; xx >= x - 1; xx--) {
                    if (!fixed[y][xx]) {
                        m[y][xx] = at < total && (words[at / 8] >> (7 - at % 8) & 1) != 0;
                        at++;
                        cells.add(new int[]{y, xx});
                    }
                }
            }
            x -= 2;
            up = !up;
        }

        boolean[][] best = null;
        int bestScore = 0;
        for (int which = 0; which < 8; which++) {
            boolean[][] trial = new boolean[n][];
            for (int y = 0; y < n; y++) {
                trial[y] = m[y].clone();
            }
            for (int[] c : cells) {
                if (mask(which, c[0], c[1])) {
                    trial[c[0]][c[1]] = !trial[c[0]][c[1]];
                }
            }
            int fmt = ((which << 10) | bch(which, 0x537, 10)) ^ 0x5412;
            for (int i = 0; i < 15; i++) {
                boolean bit = (fmt >> (14 - i) & 1) != 0;
                if (i < 6) {                            // around the top-left corner
                    trial[8][i] = bit;
                } else if (i == 6) {
                    trial[8][7] = bit;
                } else if (i == 7) {
                    trial[8][8] = bit;
                } else if (i == 8) {
                    trial[7][8] = bit;
                } else {
                    trial[14 - i][8] = bit;
                }
                if (i < 7) {                            // and split between the other two
                    trial[n - 1 - i][8] = bit;
                } else {
                    trial[8][n - 15 + i] = bit;
                }
            }
            trial[n - 8][8] = true;
            int score = penalty(trial);
            if (best == null || score < bestScore) {
                best = trial;
                bestScore = score;
            }
        }
        return best;
    }

    private static void put(boolean[][] m, boolean[][] fixed, int y, int x, boolean dark) {
        if (y >= 0 && y < m.length && x >= 0 && x < m.length) {
            m[y][x] = dark;
            fixed[y][x] = true;
        }
    }

    /** For checking against the designer's: each row as 1s and 0s. Run as: java Qr.java "some text" */
    public static void main(String[] args) {
        for (String text : args) {
            boolean[][] m = matrix(text);
            if (m == null) {
                System.out.println("too long");
                continue;
            }
            for (boolean[] row : m) {
                StringBuilder line = new StringBuilder();
                for (boolean cell : row) {
                    line.append(cell ? '1' : '0');
                }
                System.out.println(line);
            }
            System.out.println();
        }
    }
}
