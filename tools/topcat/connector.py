#!/usr/bin/env python3
"""TopCat connector: an MCP server that lets an assistant ask your machines' tools for things.

It is the caller side of TopCat in one small, dependency-free file: standard-library Python only, the same
as the agent and the hub. Point it at your hub with a caller key and it offers four tools over MCP
(stdio): list the machines that are connected, see what one can be asked, ask it to run a command, and
read back a long job's output.

    TOPCAT_HUB   your hub, e.g. https://api.tiny-web.uk/topcat.php   (required)
    TOPCAT_KEY   your caller key: on a TinyWeb-hosted hub, your TinyWeb API key   (required)

Add it to an MCP client (Claude Desktop, say) as a command:

    {"mcpServers": {"topcat": {
        "command": "python3", "args": ["/path/to/tools/topcat/connector.py"],
        "env": {"TOPCAT_HUB": "https://api.tiny-web.uk/topcat.php", "TOPCAT_KEY": "YOUR-CALLER-KEY"}}}}

Safety is the hub's and the machine's, not the connector's: a command's level (look / do / ask) and the
one switch on each machine decide what actually runs, and anything at the 'ask' level waits for your yes
on the machine itself. The connector only carries the asking.
"""
import json
import os
import sys
import urllib.error
import urllib.request

HUB = os.environ.get("TOPCAT_HUB", "").rstrip("/")
KEY = os.environ.get("TOPCAT_KEY", "")
NAME = "topcat"
VERSION = "0.2"

TOOLS = [
    {
        "name": "machines",
        "description": "List the machines connected to your hub right now: each one's name, when it was last seen, "
                       "and the apps (tools) it offers. Start here to see what you can ask.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "call",
        "description": "Ask one machine's app to run a command, and get the answer back. 'look'-level commands read "
                       "and return at once; 'do'-level ones change things on the machine; 'ask'-level ones go out "
                       "into the world or can't be undone and wait for the owner's yes on the machine itself. For a "
                       "long job (a build, say) pass background=true: you get a job id, then read its output with the "
                       "'job' tool.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "machine": {"type": "string", "description": "The machine's name (from the 'machines' tool)."},
                "app": {"type": "string", "description": "The app/tool on that machine, e.g. 'bob' or 'topcat'."},
                "command": {"type": "string", "description": "The command the app offers, e.g. 'status', 'build', 'shell'."},
                "args": {"type": "object", "description": "The command's parameters, as a JSON object.", "additionalProperties": True},
                "yes": {"type": "boolean", "description": "Confirm an 'ask'-level command. The machine still has the final say."},
                "background": {"type": "boolean", "description": "Start a long job and return a job id instead of waiting."},
            },
            "required": ["machine", "app", "command"],
            "additionalProperties": False,
        },
    },
    {
        "name": "shell",
        "description": "A shortcut for 'call' with app='topcat', command='shell': run a shell command on a machine "
                       "(only where the machine has its shell switched on). Pass background=true for anything slow.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "machine": {"type": "string"},
                "command": {"type": "string", "description": "The shell command line to run."},
                "background": {"type": "boolean"},
            },
            "required": ["machine", "command"],
            "additionalProperties": False,
        },
    },
    {
        "name": "job",
        "description": "Read a background job's output: whether it is still running, its exit code when done, and the "
                       "last lines so far. Use the job id returned by a 'call'/'shell' started with background=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "machine": {"type": "string"},
                "job": {"type": "string", "description": "The job id from a background call."},
                "lines": {"type": "integer", "description": "How many trailing lines to return (default 200)."},
            },
            "required": ["machine", "job"],
            "additionalProperties": False,
        },
    },
]


def hub(action, body=None, timeout=90):
    """One request to the hub. Caller actions carry the key as a Bearer token; the hub decides what you may see."""
    if not HUB or not KEY:
        raise RuntimeError("TOPCAT_HUB and TOPCAT_KEY must both be set in the environment")
    url = f"{HUB}?a={action}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET",
                                 headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        try:
            return {"error": json.loads(detail).get("error", detail), "status": e.code}
        except Exception:
            return {"error": detail or str(e), "status": e.code}


def do_call(a):
    body = {"machine": a["machine"], "app": a["app"], "command": a["command"],
            "args": dict(a.get("args") or {}), "yes": bool(a.get("yes"))}
    if a.get("background"):
        body["args"]["background"] = True
    return hub("call", body)


def do_shell(a):
    body = {"machine": a["machine"], "app": "topcat", "command": "shell",
            "args": {"command": a["command"], **({"background": True} if a.get("background") else {})}, "yes": True}
    return hub("call", body)


def do_job(a):
    body = {"machine": a["machine"], "app": "topcat", "command": "job",
            "args": {"job": a["job"], "lines": int(a.get("lines") or 200)}}
    return hub("call", body)


def run_tool(name, a):
    if name == "machines":
        return hub("machines")
    if name == "call":
        return do_call(a)
    if name == "shell":
        return do_shell(a)
    if name == "job":
        return do_job(a)
    raise KeyError(f"no tool called {name!r}")


# --- MCP over stdio: newline-delimited JSON-RPC 2.0 -------------------------------------------------

def reply(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def result(rid, payload):
    reply({"jsonrpc": "2.0", "id": rid, "result": payload})


def error(rid, code, message):
    reply({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}})


def handle(req):
    method = req.get("method")
    rid = req.get("id")
    if method == "initialize":
        result(rid, {"protocolVersion": "2024-11-05",
                     "capabilities": {"tools": {}},
                     "serverInfo": {"name": NAME, "version": VERSION}})
    elif method in ("notifications/initialized", "initialized"):
        pass  # a notification: no reply
    elif method == "ping":
        result(rid, {})
    elif method == "tools/list":
        result(rid, {"tools": TOOLS})
    elif method == "tools/call":
        params = req.get("params") or {}
        tool = params.get("name", "")
        args = params.get("arguments") or {}
        try:
            out = run_tool(tool, args)
            text = json.dumps(out, indent=2, ensure_ascii=False)
            is_error = isinstance(out, dict) and bool(out.get("error"))
            result(rid, {"content": [{"type": "text", "text": text}], "isError": is_error})
        except Exception as exc:
            result(rid, {"content": [{"type": "text", "text": f"error: {exc}"}], "isError": True})
    elif rid is not None:
        error(rid, -32601, f"method not found: {method}")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        try:
            handle(req)
        except Exception as exc:                 # never die on one bad message
            if isinstance(req, dict) and req.get("id") is not None:
                error(req.get("id"), -32603, str(exc))


if __name__ == "__main__":
    main()
