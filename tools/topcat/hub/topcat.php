<?php
/*
 * TopCat's hub (api.tiny-web.uk/topcat.php): a post office between whoever asks (Claude, a script, TopCat's window)
 * and your machines. Machines dial out to it and wait for work, so nothing at home listens and no router port is
 * opened. What can be asked is each machine's app API (vml/appapi.py: look, do, ask), never a raw shell.
 *
 *   machine:  POST ?a=next     {machine, apps?}            waits up to 20 s for a request: {id, app, command, args, yes}
 *             POST ?a=answer   {machine, id, result}
 *   caller:   POST ?a=call     {machine, app, command, args?, yes?}   waits up to 50 s: the answer, or {pending: id}
 *             GET  ?a=result&id=N                          a pending one's answer
 *             GET  ?a=machines                             your machines: who's there, when last seen, what each can be asked
 *             POST ?a=claim    {machine}                   make a machine yours (first come; then only you can drive it)
 *
 * A caller's token is their TinyWeb API key (validated against tinyweb.api_tokens via TinyApiAuth); each caller
 * sees and drives only the machines they own. Machines authenticate with a per-machine key in
 * /etc/topcat/tokens.json (readable by www-data only); legacy caller keys there still work (unscoped), for tooling:
 *   {"callers": {"steve": "LONG-RANDOM"}, "machines": {"a9": "LONG-RANDOM", "a8": "..."}}
 */
declare(strict_types=1);
header('Content-Type: application/json');
header('Cache-Control: no-store');

define('TOKENS', getenv('TOPCAT_TOKENS') ?: '/etc/topcat/tokens.json');
define('DB', getenv('TOPCAT_DB') ?: '/var/lib/topcat/topcat.db');

function out($x, int $code = 200): void { http_response_code($code); echo json_encode($x, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE); exit; }

// A caller may present their TinyWeb API key instead of a hub token. Validated the same way every other Tiny*
// service does. Guarded hard: if the shared auth or its DB isn't reachable, this just returns null (no key match)
// so the rest of the hub — and legacy hub tokens — keep working.
function api_user(): ?int {
    $f = '/var/www/shared/TinyApiAuth.php';
    if (!is_file($f) || !is_file('/var/www/shared/TinyDb.php')) return null;
    try {
        require_once $f;
        $uid = TinyApiAuth::authenticateAny();   // reads the Bearer header itself
        return $uid ? (int)$uid : null;
    } catch (\Throwable $e) {
        return null;
    }
}

// Returns [kind, name, owner] where owner is the caller's TinyWeb user_id (int) when the token is an API key,
// or null for a machine or a legacy hub caller (which stays unscoped).
function who(PDO $pdo): array {
    $t = json_decode((string)@file_get_contents(TOKENS), true) ?: [];
    $h = $_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '';
    $given = preg_match('/^Bearer\s+(\S+)$/', $h, $m) ? $m[1] : '';
    if (strlen($given) < 24) out(['error' => 'no token'], 401);
    foreach (($t['machines'] ?? []) as $name => $tok) if (hash_equals((string)$tok, $given)) return ['machine', (string)$name, null];
    foreach (($t['callers'] ?? []) as $name => $tok) if (hash_equals((string)$tok, $given)) return ['caller', (string)$name, null];
    $aq = $pdo->prepare('SELECT id, adopted FROM anon WHERE key = ?');
    $aq->execute([hash('sha256', $given)]);
    if ($r = $aq->fetch()) return $r['adopted'] !== null
        ? ['caller', 'u' . (int)$r['adopted'], (int)$r['adopted']]     // this key was adopted into an account
        : ['caller', 'anon' . (int)$r['id'], -(int)$r['id']];          // an anonymous owner (negative id, its own namespace)
    $uid = api_user();
    if ($uid !== null) return ['caller', 'u' . $uid, $uid];
    out(['error' => 'not a token TopCat knows (a caller uses their TinyWeb API key)'], 401);
}

function db(): PDO {
    $new = !file_exists(DB);
    $pdo = new PDO('sqlite:' . DB, null, null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION, PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC]);
    $pdo->exec('PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;');
    $pdo->exec('CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY, machine TEXT, caller TEXT, app TEXT, command TEXT,
                args TEXT, yes INTEGER, status TEXT DEFAULT \'queued\', result TEXT, asked REAL, taken REAL, answered REAL);
                CREATE TABLE IF NOT EXISTS machines (name TEXT PRIMARY KEY, seen REAL, apps TEXT, address TEXT, owner INTEGER, uuid TEXT);
                CREATE TABLE IF NOT EXISTS anon (id INTEGER PRIMARY KEY, key TEXT UNIQUE, created REAL, ip TEXT, adopted INTEGER);
                CREATE INDEX IF NOT EXISTS rq ON requests (machine, status);');
    try { $pdo->exec('ALTER TABLE machines ADD COLUMN owner INTEGER'); } catch (\Throwable $e) {}   // migrate older DBs
    try { $pdo->exec('ALTER TABLE machines ADD COLUMN uuid TEXT'); } catch (\Throwable $e) {}
    if ($new) @chmod(DB, 0600);
    return $pdo;
}

function body(): array { return json_decode((string)file_get_contents('php://input'), true) ?: []; }

$a = $_GET['a'] ?? '';
$pdo = db();
set_time_limit(70);

// A brand-new anonymous owner key: no token needed (this is how you GET one). Rate-limited per address so it
// can't be farmed. The key is the owner - every machine carrying it shares one namespace; adopt links it to
// a TinyWeb account later for recovery.
if ($a === 'mint') {
    $ip = $_SERVER['REMOTE_ADDR'] ?? '';
    $c = $pdo->prepare('SELECT COUNT(*) n FROM anon WHERE ip = ? AND created > ?');
    $c->execute([$ip, microtime(true) - 86400]);
    if ((int)$c->fetch()['n'] >= 20) out(['error' => 'too many new keys from here today - try later'], 429);
    $key = bin2hex(random_bytes(24));
    $pdo->prepare('INSERT INTO anon (key, created, ip) VALUES (?, ?, ?)')->execute([hash('sha256', $key), microtime(true), $ip]);
    out(['key' => $key, 'owner' => -(int)$pdo->lastInsertId(),
         'note' => 'This key owns your machines - put it in TopCat on each one. With no account it is the only way back in, so keep it safe or adopt it into a TinyWeb account.']);
}

[$kind, $name, $owner] = who($pdo);

// A machine checking in (next) or answering (answer). Two ways authenticate: a legacy per-machine token (it names
// itself), OR a caller holding an owner key / TinyWeb API key (it names itself in the body, and the machine is
// registered - and auto-claimed - under that owner). So a machine needs no tokens.json entry: its owner key is enough.
$machine_mode = ($kind === 'machine') || (($a === 'next' || $a === 'answer') && $owner !== null);
if ($machine_mode) {
    $b = body();
    if ($kind === 'machine') {
        $mname = $name;
    } else {
        $mname = (string)($b['machine'] ?? '');
        if (!preg_match('/^[\w.-]{1,64}$/', $mname)) out(['error' => 'machine name?'], 400);
        $chk = $pdo->prepare('SELECT owner FROM machines WHERE name = ?');
        $chk->execute([$mname]);
        $ex = $chk->fetch();
        if ($ex && $ex['owner'] !== null && (int)$ex['owner'] !== $owner) out(['error' => 'a machine called that is owned by someone else'], 403);
    }
    if ($a === 'next') {
        $apps = isset($b['apps']) ? json_encode($b['apps']) : null;
        $uuid = ((string)($b['uuid'] ?? '')) !== '' ? (string)$b['uuid'] : null;
        $pdo->prepare('INSERT INTO machines (name, seen, apps, address, uuid) VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(name) DO UPDATE SET seen = excluded.seen, address = excluded.address,
                       apps = COALESCE(excluded.apps, machines.apps), uuid = COALESCE(machines.uuid, excluded.uuid)')
            ->execute([$mname, microtime(true), $apps, $_SERVER['REMOTE_ADDR'] ?? '', $uuid]);
        if ($kind !== 'machine') {                           // an owner-key agent claims its own machine automatically
            $pdo->prepare('UPDATE machines SET owner = ? WHERE name = ? AND (owner IS NULL OR owner = ?)')
                ->execute([$owner, $mname, $owner]);
        }
        // (a request nobody picked up in 10 minutes is dropped: whoever asked has long given up)
        $pdo->prepare("UPDATE requests SET status = 'expired' WHERE status = 'queued' AND asked < ?")->execute([microtime(true) - 600]);
        $end = microtime(true) + 20;
        do {
            $pdo->beginTransaction();
            $r = $pdo->prepare("SELECT * FROM requests WHERE machine = ? AND status = 'queued' ORDER BY id LIMIT 1");
            $r->execute([$mname]);
            $job = $r->fetch();
            if ($job) {
                $pdo->prepare("UPDATE requests SET status = 'taken', taken = ? WHERE id = ?")->execute([microtime(true), $job['id']]);
                $pdo->commit();
                out(['id' => (int)$job['id'], 'app' => $job['app'], 'command' => $job['command'],
                     'args' => json_decode($job['args'] ?: '{}', true) ?: new stdClass(), 'yes' => (bool)$job['yes'], 'caller' => $job['caller']]);
            }
            $pdo->commit();
            usleep(500000);
            $pdo->prepare('UPDATE machines SET seen = ? WHERE name = ?')->execute([microtime(true), $mname]);
        } while (microtime(true) < $end);
        out(['id' => null]);
    }
    if ($a === 'answer') {
        $pdo->prepare("UPDATE requests SET status = 'answered', result = ?, answered = ? WHERE id = ? AND machine = ?")
            ->execute([json_encode($b['result'] ?? null, JSON_UNESCAPED_UNICODE), microtime(true), (int)($b['id'] ?? 0), $mname]);
        out(['ok' => true]);
    }
    out(['error' => 'a machine can ask next or answer'], 400);
}

// a caller
function result(PDO $pdo, int $id, float $wait): array {
    $end = microtime(true) + $wait;
    do {
        $r = $pdo->prepare('SELECT status, result FROM requests WHERE id = ?');
        $r->execute([$id]);
        $row = $r->fetch();
        if (!$row) return ['error' => 'no such request'];
        if ($row['status'] === 'answered') return json_decode($row['result'], true) ?? [];
        if ($row['status'] === 'expired') return ['error' => 'the machine never picked it up (asleep? off?)'];
        usleep(300000);
    } while (microtime(true) < $end);
    return ['pending' => $id, 'status' => $row['status'], 'note' => 'not answered yet: ask for ?a=result&id=' . $id];
}

// a caller may only touch a machine they own; a legacy (unscoped) caller may touch any. Returns true if allowed.
function owns(PDO $pdo, ?int $owner, string $machine): bool {
    if ($owner === null) return true;                 // legacy hub caller: unscoped, as before
    $s = $pdo->prepare('SELECT owner FROM machines WHERE name = ?');
    $s->execute([$machine]);
    $row = $s->fetch();
    return $row && $row['owner'] !== null && (int)$row['owner'] === $owner;
}

if ($a === 'claim') {
    if ($owner === null) out(['error' => 'claiming a machine needs your TinyWeb API key'], 403);
    $b = body();
    $mc = (string)($b['machine'] ?? '');
    if (!preg_match('/^[\w.-]{1,64}$/', $mc)) out(['error' => 'machine?'], 400);
    $pdo->prepare('UPDATE machines SET owner = ? WHERE name = ? AND (owner IS NULL OR owner = ?)')->execute([$owner, $mc, $owner]);
    $chk = $pdo->prepare('SELECT owner FROM machines WHERE name = ?');
    $chk->execute([$mc]);
    $row = $chk->fetch();
    if (!$row) out(['error' => 'no machine by that name has connected yet'], 404);
    if ((int)$row['owner'] !== $owner) out(['error' => 'that machine is already owned by someone else'], 403);
    out(['ok' => true, 'machine' => $mc, 'owner' => $owner]);
}
if ($a === 'adopt') {
    if ($owner === null || $owner < 0) out(['error' => 'adopting a key into an account needs your TinyWeb API key (sign in first)'], 403);
    $b = body();
    $ak = (string)($b['anon_key'] ?? '');
    if (strlen($ak) < 24) out(['error' => 'anon_key?'], 400);
    $st = $pdo->prepare('SELECT id, adopted FROM anon WHERE key = ?');
    $st->execute([hash('sha256', $ak)]);
    $row = $st->fetch();
    if (!$row) out(['error' => 'no such key'], 404);
    if ($row['adopted'] !== null) out(['error' => 'that key is already linked to an account'], 409);
    $mv = $pdo->prepare('UPDATE machines SET owner = ? WHERE owner = ?');
    $mv->execute([$owner, -(int)$row['id']]);
    $pdo->prepare('UPDATE anon SET adopted = ? WHERE id = ?')->execute([$owner, (int)$row['id']]);
    out(['ok' => true, 'adopted_into' => $owner, 'machines_moved' => $mv->rowCount()]);
}
if ($a === 'machines') {
    if ($owner === null) {
        $rows = $pdo->query('SELECT name, seen, apps, address, uuid FROM machines ORDER BY name')->fetchAll();
    } else {
        $q = $pdo->prepare('SELECT name, seen, apps, address, uuid FROM machines WHERE owner = ? ORDER BY name');
        $q->execute([$owner]);
        $rows = $q->fetchAll();
    }
    $now = microtime(true);
    out(array_map(fn($m) => ['machine' => $m['name'], 'online' => ($now - (float)$m['seen']) < 60,
        'seen_seconds_ago' => (int)($now - (float)$m['seen']), 'uuid' => $m['uuid'], 'apps' => json_decode($m['apps'] ?: '[]', true)], $rows));
}
if ($a === 'call') {
    $b = body();
    foreach (['machine', 'app', 'command'] as $k) if (!preg_match('/^[\w.-]{1,64}$/', (string)($b[$k] ?? ''))) out(['error' => "$k?"], 400);
    if (!owns($pdo, $owner, (string)$b['machine'])) out(['error' => 'not your machine (claim it first with ?a=claim)'], 403);
    $pdo->prepare('INSERT INTO requests (machine, caller, app, command, args, yes, asked) VALUES (?, ?, ?, ?, ?, ?, ?)')
        ->execute([$b['machine'], $name, $b['app'], $b['command'], json_encode($b['args'] ?? new stdClass()), !empty($b['yes']) ? 1 : 0, microtime(true)]);
    out(result($pdo, (int)$pdo->lastInsertId(), 50));
}
if ($a === 'result') out(result($pdo, (int)($_GET['id'] ?? 0), 25));
out(['error' => 'ask for machines, call, result, claim or adopt (or mint, no token, for a new owner key)'], 400);
