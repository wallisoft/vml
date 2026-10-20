# TopCat

TopCat lets you, and Claude, ask your machines' apps for things from anywhere: Pat's books from your phone, a Bob build started while you're out, all without opening anything at home. Each machine answers only what its apps' API allows ([The apps' API](../../../docs/App-API.md)): look, do, or ask with your yes. Never a raw shell.

## How it fits together

```
  you / Claude  --HTTPS-->  the hub (api.tiny-web.uk/topcat.php)  <--HTTPS--  the agent on each machine
                                                                               (asks the hub for work, every 20 s)
```

- **The agent** (`tools/topcat/agent.py`) runs on each of your machines as a background service. It dials *out* to the hub and waits for a request; nothing on your machine listens, and no router port is opened. It works from any Wi-Fi.
- **The hub** is one PHP file on your server. It holds requests until the right machine picks them up, and the answers until whoever asked collects them. Anything not picked up in ten minutes is dropped.
- **Callers** (you, Claude, a script) ask the hub with their key: which machine, which app, which command.

## The window

Open `apps/topcat/TopCat.vmlproj` on a machine to see its side:

- **Let TopCat in**: on, the agent runs and starts at every login; off, it stops and nobody can ask this machine anything.
- **The light**: green, connected; amber, trying to reach the hub (asleep? no Wi-Fi?); grey, off.
- **Callers may**: look; look and do; or do and ask. A cap on top of each command's own level.
- **Who asked what**: every request, newest first: when, who, what, its level and the answer.
- **A build, as it goes**: when something starts a build, its lines stream in here as it runs, and it ends green or red. Pick any earlier build to see it again.

A desktop notice pops up whenever a caller asks for something that changes things.

## Setting up

You need: the Visualised repo on the machine, `ssh` to your server with sudo there, and the server running nginx and PHP with SQLite.

1. Make two keys: one for the caller, one for the machine.
2. On the server: `/etc/topcat/tokens.json` with them, readable by the web server only, and the hub in a web folder:
   ```
   {"callers": {"claude": "CALLER-KEY"}, "machines": {"a9": "MACHINE-KEY"}}
   ```
   with `/var/lib/topcat` writable by the web server (the hub keeps its queue there, in SQLite).
3. On the machine: `~/.config/topcat/agent.json`, readable by you alone:
   ```
   {"hub": "https://api.tiny-web.uk/topcat.php", "machine": "a9", "token": "MACHINE-KEY", "level": "ask"}
   ```
4. `python3 tools/topcat/agent.py --install` runs it now and at every login (a systemd user service).

Another machine is another line under `machines` and its own `agent.json`. To shut a caller or a machine out, change or remove its key in `tokens.json`: it takes effect at once.

## Asking

With the caller's key, as `Authorization: Bearer KEY`:

| Request | What it does |
|---|---|
| `GET ?a=machines` | Every machine: online or not, when last seen, its apps and their commands |
| `POST ?a=call` `{"machine": "a9", "app": "pat", "command": "report"}` | Asks, and waits up to 50 seconds for the answer |
| ... with `"args": {...}` | The command's parameters |
| ... with `"yes": true` | Your yes, for an "ask" command |
| `GET ?a=result&id=N` | The answer to one that took longer than 50 seconds |

The agent answers three of its own too, as app `topcat`: **hello** (the machine, its level, its apps), **apps** (everything they can be asked), and **job** (a background job: still going? its last lines).

## Safety

- Nothing listens at home: the agent only makes outgoing requests.
- Only what an app's `api.vml` offers can be asked, with every parameter checked and quoted; there's no shell.
- "Ask" commands need a yes with each request, and the machine's own cap can forbid them entirely.
- Keys are long and random, compared in constant time, and kept in files only their owners can read. Everything travels over HTTPS.
- Every request is in the window's log, and in the hub's database.
