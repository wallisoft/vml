<?php
// Visualised Link: pairing by pressing together. Part of the relay (link.php hands over to this when asked ?p=).
//
// Two apps that have nothing in common yet, no code scanned or copied, each press "pair" within a few seconds
// of each other. This finds the two that pressed together and passes each the other's public key. From the
// keys the apps work out a secret between themselves, which never comes here, and each shows three words made
// from it for their people to compare: if this relay (or anyone in between) had swapped the keys, the words
// would differ.
//
//   POST ?p=go            body {"c": PROMISE}     -> {"ok": true, "id": ID}
//   GET  ?p=wait&id=ID                            -> {"ok": true, "state": "waiting" | "busy" | "gone"}
//                                                 or {"ok": true, "state": "paired", "c": the other's PROMISE, "k": the other's KEY or ""}
//   POST ?p=key&id=ID     body {"k": KEY}         -> {"ok": true}
//
// PROMISE is the SHA-256 of KEY, as 64 hex digits, and is given first: an app shows its key only once it holds
// the other's promise, so nobody can choose a key to suit one it has already seen. KEY is a P-256 public key,
// 65 bytes as base64url. ID is 32 random hex digits and is the only way to a pairing: there is nothing to guess
// at or count through.
//
// Two are paired only when they are the only two who pressed within the same five seconds, and not until a
// second and a half after the later press, so that a third pressing with them is seen. With any doubt about who
// meant whom, all of them are told "busy" and press again. (Someone pressing after two have been paired is
// simply not answered. And if the wrong two are ever paired, the words are what shows it: the app beside you
// will not have them.) A press that nobody answers is "gone" after 25 seconds, and everything here is forgotten after two minutes. From one address: 12 presses a minute
// and 60 an hour.

const PAIR_WINDOW_MS = 5000;
const PAIR_HOLD_MS = 1500;
const PAIR_GIVE_UP_MS = 25000;
const PAIR_FORGET_MS = 120000;
const PRESSES_A_MINUTE = 12;
const PRESSES_AN_HOUR = 60;

try {
    $db->exec("CREATE TABLE IF NOT EXISTS pairs (id TEXT PRIMARY KEY, at INTEGER NOT NULL, state TEXT NOT NULL, promise TEXT NOT NULL, pub TEXT NOT NULL DEFAULT '', peer TEXT NOT NULL DEFAULT '')");
    $db->exec('CREATE INDEX IF NOT EXISTS pairs_waiting ON pairs (state, at)');
} catch (Throwable $e) {
    refuse(503, 'the relay is not available');
}

$ms = (int) floor(microtime(true) * 1000);
$what = $_GET['p'] ?? '';
$post = $_SERVER['REQUEST_METHOD'] === 'POST';
$in = $post ? json_decode(file_get_contents('php://input', false, null, 0, 2000), true) : null;
$id = $_GET['id'] ?? '';
if ($what !== 'go' && !preg_match('/^[0-9a-f]{32}$/', $id)) refuse(400, 'no such pairing');

// Settle where this press stands: still waiting, paired with the one other who pressed with it, or not.
function settle(PDO $db, string $id, int $ms): ?array {
    $near = fn(int $at) => [$at - PAIR_WINDOW_MS, $at + PAIR_WINDOW_MS];
    $db->exec('BEGIN IMMEDIATE');                    // one at a time: two can't each pair with a different third
    try {
        $q = $db->prepare('SELECT * FROM pairs WHERE id = ?');
        $q->execute([$id]);
        $me = $q->fetch(PDO::FETCH_ASSOC);
        $q->closeCursor();
        if ($me && $me['state'] === 'waiting') {
            $q = $db->prepare("SELECT id, at FROM pairs WHERE state = 'waiting' AND id <> ? AND at > ? AND at < ?");
            $q->execute([$id, ...$near((int) $me['at'])]);
            $others = $q->fetchAll(PDO::FETCH_ASSOC);
            $busy = fn(int $at) => $db->prepare("UPDATE pairs SET state = 'busy' WHERE state = 'waiting' AND at > ? AND at < ?")->execute($near($at));
            if (count($others) > 1) {
                $busy((int) $me['at']);
            } elseif (count($others) === 1 && $ms - max((int) $me['at'], (int) $others[0]['at']) < PAIR_HOLD_MS) {
                // two so far: hold on a moment, in case a third presses with them
            } elseif (count($others) === 1) {
                $q = $db->prepare("SELECT COUNT(*) FROM pairs WHERE state = 'waiting' AND id <> ? AND id <> ? AND at > ? AND at < ?");
                $q->execute([$id, $others[0]['id'], ...$near((int) $others[0]['at'])]);
                if (one($q)) {             // the other has someone else as near: who meant whom?
                    $busy((int) $others[0]['at']);
                    $busy((int) $me['at']);
                } else {
                    $u = $db->prepare("UPDATE pairs SET state = 'paired', peer = ? WHERE id = ? AND state = 'waiting'");
                    $u->execute([$others[0]['id'], $id]);
                    $u->execute([$id, $others[0]['id']]);
                }
            } elseif ($ms - (int) $me['at'] > PAIR_GIVE_UP_MS) {
                $db->prepare("UPDATE pairs SET state = 'gone' WHERE id = ?")->execute([$id]);
            }
            $q = $db->prepare('SELECT * FROM pairs WHERE id = ?');
            $q->execute([$id]);
            $me = $q->fetch(PDO::FETCH_ASSOC);
            $q->closeCursor();
        }
        $db->exec('COMMIT');
        return $me ?: null;
    } catch (Throwable $e) {
        $db->exec('ROLLBACK');
        throw $e;
    }
}

try {
    if ($what === 'go' && $post) {
        $promise = is_array($in) ? ($in['c'] ?? '') : '';
        if (!is_string($promise) || !preg_match('/^[0-9a-f]{64}$/', $promise)) refuse(400, 'that is not a promise');
        if (count_one($db, "p:$who", intdiv($now, 60)) > PRESSES_A_MINUTE || count_one($db, "h:p$who", intdiv($now, 3600)) > PRESSES_AN_HOUR)
            refuse(429, 'too many tries: wait a minute');
        $db->prepare('DELETE FROM pairs WHERE at < ?')->execute([$ms - PAIR_FORGET_MS]);
        $id = bin2hex(random_bytes(16));
        $db->prepare("INSERT INTO pairs (id, at, state, promise) VALUES (?, ?, 'waiting', ?)")->execute([$id, $ms, $promise]);
        answer(200, ['ok' => true, 'id' => $id]);
    }

    if ($what === 'wait' && !$post) {
        $me = settle($db, $id, $ms);
        if (!$me) refuse(404, 'no such pairing');
        if ($me['state'] !== 'paired') answer(200, ['ok' => true, 'state' => $me['state']]);
        $q = $db->prepare('SELECT promise, pub FROM pairs WHERE id = ?');
        $q->execute([$me['peer']]);
        $other = $q->fetch(PDO::FETCH_ASSOC);
        $q->closeCursor();
        if (!$other) answer(200, ['ok' => true, 'state' => 'gone']);
        answer(200, ['ok' => true, 'state' => 'paired', 'c' => $other['promise'], 'k' => $other['pub']]);
    }

    if ($what === 'key' && $post) {
        $key = is_array($in) ? ($in['k'] ?? '') : '';
        if (!is_string($key) || !preg_match('/^[A-Za-z0-9_-]{87}$/', $key)) refuse(400, 'that is not a key');
        $q = $db->prepare('SELECT state, promise FROM pairs WHERE id = ?');
        $q->execute([$id]);
        $me = $q->fetch(PDO::FETCH_ASSOC);
        $q->closeCursor();
        if (!$me) refuse(404, 'no such pairing');
        if ($me['state'] !== 'paired') refuse(409, 'not paired yet');
        if (!hash_equals($me['promise'], hash('sha256', base64_decode(strtr($key, '-_', '+/'))))) refuse(400, 'that is not the key that was promised');
        $db->prepare("UPDATE pairs SET pub = ? WHERE id = ? AND pub = ''")->execute([$key, $id]);
        answer(200, ['ok' => true]);
    }
} catch (Throwable $e) {
    error_log('link pairing: ' . $e->getMessage());
    refuse(503, 'the relay is busy: try again');
}
refuse(400, 'go, wait or key');
