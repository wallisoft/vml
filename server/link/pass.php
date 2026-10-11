<?php
// Visualised Link: who the relay carries links for. Part of the relay (link.php uses this).
//
// Link is free to the people who use an app, and part of Visualised Pro for whoever makes one. A Pro licence gets
// its holder a pass, which Visualised puts into the apps they save and export; an app shows its pass with each
// message, and its links are carried in full. An app with no pass still works, on the free allowance: enough to
// try Link and to build with it, not enough to run a service on.
//
//   POST ?pass      body {"key": LICENCE KEY}     -> {"ok": true, "pass": PASS}
//
// The licence key is checked here just as Visualised checks it (an Ed25519 signature by tiny-web.uk), and is not
// kept. PASS is "VP1-" + the licence's id + "-" + its last day (YYYYMMDD, or 0 for none) + "." + a seal only this
// relay can make. Unlike the key, a pass is not a secret worth much: it travels inside every app its holder
// publishes, and all it does is ask this relay to carry links. If one is abused it can be turned off here:
//
//   sudo -u www-data sqlite3 /var/lib/vml-link/link.db "INSERT INTO revoked VALUES ('the licence id')"
//
// and what each pass has sent, a day at a time, is in the table "used".

const LICENCE_PUBLIC_KEY = 'f8adda3be6d239d1b78bd0599d1b2924b0e02cfea2f1f63b69e3c256f4207ae5';   // the same as vml/licence.py
const FREE_MESSAGES_AN_HOUR = 100;       // into one link, with no pass
const FREE_KEEP_SECONDS = 3600;          // and how long its messages are kept
const PASSES_AN_HOUR = 20;               // askings for a pass, from one address

function b64url(string $raw): string { return rtrim(strtr(base64_encode($raw), '+/', '-_'), '='); }
function unb64url(string $text): string { return (string) base64_decode(strtr($text, '-_', '+/')); }

// The relay's own secret, which seals passes. Made the first time it is wanted, beside the database.
function relay_secret(string $db_path): string {
    $file = dirname($db_path) . '/pass.secret';
    $secret = @file_get_contents($file);
    if ($secret === false || strlen($secret) !== 32) {
        $secret = random_bytes(32);
        $old = umask(0077);
        $made = @file_put_contents($file, $secret, LOCK_EX);
        umask($old);
        if ($made !== 32) refuse(503, 'the relay is not available');
        $secret = (string) file_get_contents($file);          // (if two made one at once, both use the one that stayed)
    }
    return $secret;
}

function pass_seal(string $secret, string $id, string $until): string {
    return b64url(substr(hash_hmac('sha256', "pass|$id|$until", $secret, true), 0, 16));
}

// What a genuine, current licence key says: [id, last day or '0']. null for anything else.
function licence_of(string $key): ?array {
    $key = preg_replace('/[\s"\'<>]+/', '', $key);
    $public = ($_SERVER['LINK_LICENCE_PUBLIC'] ?? '') ?: (getenv('LINK_LICENCE_PUBLIC') ?: LICENCE_PUBLIC_KEY);
    if (!str_starts_with($key, 'VSL1-') || substr_count($key, '.') !== 1 || strlen($public) !== 64) return null;
    [$payload, $signature] = array_map('unb64url', explode('.', substr($key, 5)));
    if (strlen($signature) !== 64 || !sodium_crypto_sign_verify_detached($signature, $payload, hex2bin($public))) return null;
    $f = explode('|', $payload) + [1 => '', 2 => '', 3 => '', 4 => ''];
    if (!in_array($f[0], ['pro', 'enterprise'], true) || !preg_match('/^[A-Za-z0-9_-]{1,40}$/', $f[2])) return null;
    if ($f[4] !== '' && (!preg_match('/^\d{8}$/', $f[4]) || $f[4] < date('Ymd'))) return null;
    return [$f[2], $f[4] === '' ? '0' : $f[4]];
}

// The licence id a pass stands for, or '' if it isn't one of ours, has run out, or has been turned off.
function pass_holder(PDO $db, string $db_path, string $pass): string {
    if (!preg_match('/^VP1-([A-Za-z0-9_-]{1,40})-(0|\d{8})\.([A-Za-z0-9_-]{22})$/', $pass, $m)) return '';
    if (!hash_equals(pass_seal(relay_secret($db_path), $m[1], $m[2]), $m[3])) return '';
    if ($m[2] !== '0' && $m[2] < date('Ymd')) return '';
    $q = $db->prepare('SELECT 1 FROM revoked WHERE id = ?');
    $q->execute([$m[1]]);
    return one($q) ? '' : $m[1];
}

$db->exec('CREATE TABLE IF NOT EXISTS revoked (id TEXT PRIMARY KEY)');
$db->exec('CREATE TABLE IF NOT EXISTS used (id TEXT NOT NULL, day INTEGER NOT NULL, n INTEGER NOT NULL, PRIMARY KEY (id, day))');
$db->exec('CREATE TABLE IF NOT EXISTS carried (channel TEXT PRIMARY KEY, id TEXT NOT NULL, at INTEGER NOT NULL)');

if (isset($_GET['pass'])) {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') refuse(405, 'POST');
    if (count_one($db, "h:k$who", intdiv($now, 3600)) > PASSES_AN_HOUR) refuse(429, 'too many tries: wait an hour');
    $in = json_decode(file_get_contents('php://input', false, null, 0, 4000), true);
    $licence = licence_of(is_array($in) && is_string($in['key'] ?? null) ? $in['key'] : '');
    if (!$licence) refuse(403, 'that is not a current Visualised Pro licence');
    [$id, $until] = $licence;
    $q = $db->prepare('SELECT 1 FROM revoked WHERE id = ?');
    $q->execute([$id]);
    if (one($q)) refuse(403, 'that licence may not use the relay');
    answer(200, ['ok' => true, 'pass' => "VP1-$id-$until." . pass_seal(relay_secret($path), $id, $until)]);
}
