<?php
// Visualised Link: the relay.
//
// Two apps that have agreed a secret between themselves (by QR code, or a code copied across) pass messages
// through here. All this ever sees is a channel name, which the apps derive from their secret, and messages
// already encrypted with a key that never leaves them. It keeps each message for a day at most and cannot read
// any of them.
//
//   POST ?c=CHANNEL          body {"s": SENDER, "b": MESSAGE}       -> {"ok": true, "seq": 12}
//   GET  ?c=CHANNEL&since=N                                         -> {"ok": true, "seq": 12, "m": [{"q": 11, "s": "...", "b": "...", "t": 1791...}, ...]}
//   GET  ?c=CHANNEL&since=-1    just where the channel has got to   -> {"ok": true, "seq": 12, "m": []}
//
// CHANNEL is 32 hex digits, SENDER 16, MESSAGE up to 24,000 characters of base64. Limits keep it from being
// used as anything else: 200 messages and one day kept per channel, 120 messages a minute into a channel, and
// from one address 1,200 requests a minute and 60 new channels an hour.
//
// Settings come from the environment (or the defaults): LINK_DB, the SQLite file.

const MAX_BODY = 24000;
const KEEP_MESSAGES = 200;
const KEEP_SECONDS = 86400;
const PER_CHANNEL_A_MINUTE = 120;
const PER_ADDRESS_A_MINUTE = 1200;
const NEW_CHANNELS_AN_HOUR = 60;

header('Content-Type: application/json');
header('Cache-Control: no-store');
header('Access-Control-Allow-Origin: *');            // any page may use the relay: what it carries is unreadable anyway
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
header('Access-Control-Max-Age: 86400');
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(204); exit; }

function answer(int $code, array $what): never {
    http_response_code($code);
    echo json_encode($what);
    exit;
}
function refuse(int $code, string $why): never { answer($code, ['ok' => false, 'error' => $why]); }

$channel = $_GET['c'] ?? '';
if (!preg_match('/^[0-9a-f]{32}$/', $channel)) refuse(400, 'no such channel');

try {
    $path = ($_SERVER['LINK_DB'] ?? '') ?: (getenv('LINK_DB') ?: '/var/lib/vml-link/link.db');
    $db = new PDO('sqlite:' . $path, null, null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION, PDO::ATTR_TIMEOUT => 5]);
    $db->exec('PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=5000');
    $db->exec('CREATE TABLE IF NOT EXISTS messages (seq INTEGER PRIMARY KEY AUTOINCREMENT, channel TEXT NOT NULL, sender TEXT NOT NULL, body TEXT NOT NULL, at INTEGER NOT NULL)');
    $db->exec('CREATE INDEX IF NOT EXISTS messages_channel ON messages (channel, seq)');
    $db->exec('CREATE TABLE IF NOT EXISTS counts (what TEXT NOT NULL, slot INTEGER NOT NULL, n INTEGER NOT NULL, PRIMARY KEY (what, slot))');
} catch (Throwable $e) {
    refuse(503, 'the relay is not available');
}

$now = time();
// One more of something in this minute (or hour): how many that makes. Addresses are counted by a hash, not kept.
function count_one(PDO $db, string $what, int $slot): int {
    $db->prepare('INSERT INTO counts (what, slot, n) VALUES (?, ?, 1) ON CONFLICT (what, slot) DO UPDATE SET n = n + 1')->execute([$what, $slot]);
    $q = $db->prepare('SELECT n FROM counts WHERE what = ? AND slot = ?');
    $q->execute([$what, $slot]);
    return (int) $q->fetchColumn();
}
$who = substr(hash('sha256', 'link' . ($_SERVER['REMOTE_ADDR'] ?? '')), 0, 16);
if (count_one($db, "a:$who", intdiv($now, 60)) > PER_ADDRESS_A_MINUTE) refuse(429, 'too many requests: slow down');

if (random_int(1, 50) === 1) {                        // now and then, clear out what is old
    $db->prepare('DELETE FROM messages WHERE at < ?')->execute([$now - KEEP_SECONDS]);
    $db->prepare("DELETE FROM counts WHERE (what LIKE 'h:%' AND slot < ?) OR (what NOT LIKE 'h:%' AND slot < ?)")->execute([intdiv($now, 3600) - 2, intdiv($now, 60) - 5]);
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $raw = file_get_contents('php://input', false, null, 0, MAX_BODY + 2000);
    $in = json_decode($raw, true);
    $sender = is_array($in) ? ($in['s'] ?? '') : '';
    $body = is_array($in) ? ($in['b'] ?? '') : '';
    if (!is_string($sender) || !preg_match('/^[0-9a-f]{16}$/', $sender)) refuse(400, 'who is sending?');
    if (!is_string($body) || $body === '' || strlen($body) > MAX_BODY || !preg_match('/^[A-Za-z0-9+\/_-]+=*$/', $body)) refuse(400, 'that is not a message');
    if (count_one($db, "c:$channel", intdiv($now, 60)) > PER_CHANNEL_A_MINUTE) refuse(429, 'too many messages: slow down');
    $q = $db->prepare('SELECT 1 FROM messages WHERE channel = ? LIMIT 1');
    $q->execute([$channel]);
    if (!$q->fetchColumn() && count_one($db, "h:$who", intdiv($now, 3600)) > NEW_CHANNELS_AN_HOUR) refuse(429, 'too many new links from here: try again later');
    $db->prepare('INSERT INTO messages (channel, sender, body, at) VALUES (?, ?, ?, ?)')->execute([$channel, $sender, $body, $now]);
    $seq = (int) $db->lastInsertId();
    // only the newest are kept
    $db->prepare('DELETE FROM messages WHERE channel = ? AND seq <= (SELECT seq FROM messages WHERE channel = ? ORDER BY seq DESC LIMIT 1 OFFSET ?)')->execute([$channel, $channel, KEEP_MESSAGES]);
    answer(200, ['ok' => true, 'seq' => $seq]);
}

if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    $since = (int) ($_GET['since'] ?? 0);
    $q = $db->prepare('SELECT COALESCE(MAX(seq), 0) FROM messages WHERE channel = ?');
    $q->execute([$channel]);
    $latest = (int) $q->fetchColumn();
    $out = [];
    if ($since >= 0 && $latest > $since) {
        $q = $db->prepare('SELECT seq, sender, body, at FROM messages WHERE channel = ? AND seq > ? AND at >= ? ORDER BY seq LIMIT 100');
        $q->execute([$channel, $since, $now - KEEP_SECONDS]);
        foreach ($q as $r) $out[] = ['q' => (int) $r['seq'], 's' => $r['sender'], 'b' => $r['body'], 't' => (int) $r['at']];
    }
    answer(200, ['ok' => true, 'seq' => $latest, 'm' => $out]);
}
refuse(405, 'GET or POST');
