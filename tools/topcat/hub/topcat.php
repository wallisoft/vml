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
 *             GET  ?a=machines                             who's there, when last seen, what each can be asked
 * Every request carries a token: Authorization: Bearer TOKEN. /etc/topcat/tokens.json (readable by www-data only):
 *   {"callers": {"steve": "LONG-RANDOM"}, "machines": {"a9": "LONG-RANDOM", "a8": "..."}}
 */
declare(strict_types=1);
header('Content-Type: application/json');
header('Cache-Control: no-store');

define('TOKENS', getenv('TOPCAT_TOKENS') ?: '/etc/topcat/tokens.json');
define('DB', getenv('TOPCAT_DB') ?: '/var/lib/topcat/topcat.db');

function out($x, int $code = 200): void { http_response_code($code); echo json_encode($x, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE); exit; }

function who(): array {
    $t = json_decode((string)@file_get_contents(TOKENS), true) ?: [];
    $h = $_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '';
    $given = preg_match('/^Bearer\s+(\S+)$/', $h, $m) ? $m[1] : '';
    if (strlen($given) < 24) out(['error' => 'no token'], 401);
    foreach (($t['callers'] ?? []) as $name => $tok) if (hash_equals((string)$tok, $given)) return ['caller', (string)$name];
    foreach (($t['machines'] ?? []) as $name => $tok) if (hash_equals((string)$tok, $given)) return ['machine', (string)$name];
    out(['error' => 'not a token TopCat knows'], 401);
}

function db(): PDO {
    $new = !file_exists(DB);
    $pdo = new PDO('sqlite:' . DB, null, null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION, PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC]);
    $pdo->exec('PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;');
    $pdo->exec('CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY, machine TEXT, caller TEXT, app TEXT, command TEXT,
                args TEXT, yes INTEGER, status TEXT DEFAULT \'queued\', result TEXT, asked REAL, taken REAL, answered REAL);
                CREATE TABLE IF NOT EXISTS machines (name TEXT PRIMARY KEY, seen REAL, apps TEXT, address TEXT);
                CREATE INDEX IF NOT EXISTS rq ON requests (machine, status);');
    if ($new) @chmod(DB, 0600);
    return $pdo;
}

function body(): array { return json_decode((string)file_get_contents('php://input'), true) ?: []; }

[$kind, $name] = who();
$a = $_GET['a'] ?? '';
$pdo = db();
set_time_limit(70);

if ($kind === 'machine') {
    $b = body();
    if ($a === 'next') {
        $apps = isset($b['apps']) ? json_encode($b['apps']) : null;
        $pdo->prepare('INSERT INTO machines (name, seen, apps, address) VALUES (?, ?, ?, ?)
                       ON CONFLICT(name) DO UPDATE SET seen = excluded.seen, address = excluded.address,
                       apps = COALESCE(excluded.apps, machines.apps)')
            ->execute([$name, microtime(true), $apps, $_SERVER['REMOTE_ADDR'] ?? '']);
        // (a request nobody picked up in 10 minutes is dropped: whoever asked has long given up)
        $pdo->prepare("UPDATE requests SET status = 'expired' WHERE status = 'queued' AND asked < ?")->execute([microtime(true) - 600]);
        $end = microtime(true) + 20;
        do {
            $pdo->beginTransaction();
            $r = $pdo->prepare("SELECT * FROM requests WHERE machine = ? AND status = 'queued' ORDER BY id LIMIT 1");
            $r->execute([$name]);
            $job = $r->fetch();
            if ($job) {
                $pdo->prepare("UPDATE requests SET status = 'taken', taken = ? WHERE id = ?")->execute([microtime(true), $job['id']]);
                $pdo->commit();
                out(['id' => (int)$job['id'], 'app' => $job['app'], 'command' => $job['command'],
                     'args' => json_decode($job['args'] ?: '{}', true) ?: new stdClass(), 'yes' => (bool)$job['yes'], 'caller' => $job['caller']]);
            }
            $pdo->commit();
            usleep(500000);
            $pdo->prepare('UPDATE machines SET seen = ? WHERE name = ?')->execute([microtime(true), $name]);
        } while (microtime(true) < $end);
        out(['id' => null]);
    }
    if ($a === 'answer') {
        $pdo->prepare("UPDATE requests SET status = 'answered', result = ?, answered = ? WHERE id = ? AND machine = ?")
            ->execute([json_encode($b['result'] ?? null, JSON_UNESCAPED_UNICODE), microtime(true), (int)($b['id'] ?? 0), $name]);
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

if ($a === 'machines') {
    $rows = $pdo->query('SELECT name, seen, apps, address FROM machines ORDER BY name')->fetchAll();
    $now = microtime(true);
    out(array_map(fn($m) => ['machine' => $m['name'], 'online' => ($now - (float)$m['seen']) < 60,
        'seen_seconds_ago' => (int)($now - (float)$m['seen']), 'apps' => json_decode($m['apps'] ?: '[]', true)], $rows));
}
if ($a === 'call') {
    $b = body();
    foreach (['machine', 'app', 'command'] as $k) if (!preg_match('/^[\w.-]{1,64}$/', (string)($b[$k] ?? ''))) out(['error' => "$k?"], 400);
    $pdo->prepare('INSERT INTO requests (machine, caller, app, command, args, yes, asked) VALUES (?, ?, ?, ?, ?, ?, ?)')
        ->execute([$b['machine'], $name, $b['app'], $b['command'], json_encode($b['args'] ?? new stdClass()), !empty($b['yes']) ? 1 : 0, microtime(true)]);
    out(result($pdo, (int)$pdo->lastInsertId(), 50));
}
if ($a === 'result') out(result($pdo, (int)($_GET['id'] ?? 0), 25));
out(['error' => 'ask for machines, call or result'], 400);
