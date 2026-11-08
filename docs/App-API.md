# The apps' API

Every Visualised app can say what other programs may ask of it, in one small VML file beside it: `api.vml`. Bob and Pat have one. Anything that speaks the API can then drive them: a terminal, Claude through `vml mcp`, and TopCat, from anywhere.

## What can be asked: the three levels

Every command has a level, and the level decides who may use it and how:

| Level | Means | Example |
|---|---|---|
| **look** | Only reads. Always safe. | Pat's books, Bob's list of projects |
| **do** | Changes things here, harmlessly or reversibly. | Pat drafting a post, Bob stopping a build |
| **ask** | Goes out into the world, or can't be undone. Needs the person's **yes**, each time. | Pat sending a post, Bob building (some builds publish a release) |

Whoever runs an app can cap the level too: `VML_API_LEVEL=look` (or `do`) for everything run from that shell, and TopCat's "Callers may" setting for each machine.

## api.vml

```
@Api Pat                                        the app, and how to run its worker (from the repo it's in)
Run=python3 tools/pat/pat.py
About=Posts your news, and keeps the books on what it earned

@Command report                                 one thing it can be asked
Level=look
About=The books: totals per channel and per product
Run=report

@Command draft
Level=do
About=A first draft for every channel that's on
Param=product:integer:The product's id
Run=draft {product}

@Command send
Level=ask
About=Post an approved post
Param=post:integer:The post's id
Run=send {post}
```

- **Run** (under `@Api`) is the start of every command line; each command's **Run** is the rest of it.
- **Param** is `name:type:what it is`. Put `?` after the name when it may be left out. Types: `text`, `integer`, `json` (passed to the command as a file), or a list of choices like `draft|approved|posted`.
- In **Run**, `{name}` becomes the value, quoted for the shell, so nothing typed into a parameter can run as a command. `{name?--flag}` becomes `--flag VALUE`, or nothing if it was left out.
- **Background=yes** is for slow commands (a build): it starts, and the answer is a job to follow instead of waiting.
- A command should print its answer as JSON on its last line; anything else comes back as text.

Apps are found in `apps/*/api.vml` in the Visualised source, and in any folder named in `VML_API_PATH` (folders separated by `:`).

## From a terminal

```
python3 -m vml api                                  every app and what it can be asked
python3 -m vml api pat report                       ask one
python3 -m vml api pat draft product=1              with its parameters
python3 -m vml api pat send post=4 --yes            an "ask" one: --yes is your yes
python3 -m vml api job                              the background jobs; job ID for one
```

## From Claude

`vml mcp` (Visualised as an MCP server) has three tools for this: **apps** lists the apps and their commands, **app_call** asks one, and **app_job** follows a background job. For an "ask" command, Claude tells you what it will do and waits for your yes.

## From anywhere: TopCat

TopCat carries the same calls to your machines over the internet, without opening anything at home: see [TopCat](../apps/topcat/help/Home.md).

## Background jobs

A background command's output goes to `~/.cache/vml/jobs/ID.log`, and its exit code to `ID.exit` when it's done. Following a job gives whether it's still going, how long it's taken, and its last lines: enough to see where it's at without reading every line.
