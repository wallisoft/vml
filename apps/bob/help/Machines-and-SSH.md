# Machines and SSH

**[Home](Home.md)** · **[Getting started](Getting-Started.md)** · **[Recipes](Recipes.md)** · **[GitHub](GitHub.md)**

## Introduction

Bob builds on any machine he can reach over SSH without a password: he sends your project's source, builds it there, and brings the results back. This page adds a Windows PC and a Linux box.

## The machines file

**Project ▾ > Machines…** opens `~/.config/bob/machines.vml`:

```
@Machine here
OS=linux

@Machine a8
Host=a8
OS=windows
```

`Host` is how SSH reaches it: a name from `~/.ssh/config`, or `user@address`. A recipe's build says which machine with `Machine=a8`. Save, then pick the project again in Bob.

## Step 1: A Windows PC

On the PC, in PowerShell **as administrator**:

```
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
```

Give it this computer's key. If you sign in to the PC as an administrator, the key goes in a shared file:

```
notepad C:\ProgramData\ssh\administrators_authorized_keys
```

Paste the line from `cat ~/.ssh/id_ed25519.pub` on this computer (make a key first with `ssh-keygen -t ed25519` if you haven't one), save, then:

```
icacls C:\ProgramData\ssh\administrators_authorized_keys /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F"
```

(Not an administrator? The key goes in `C:\Users\YOU\.ssh\authorized_keys` instead.)

## Step 2: A name for it

On this computer, in `~/.ssh/config`:

```
Host a8
    HostName 192.168.1.50
    User steve
```

Try it: `ssh a8 hostname` should answer with the PC's name, no password asked. That's all Bob needs: the first build there installs Python (with winget) and its own build tools, so it takes a few minutes longer; the ones after are quicker.

## Step 3: A Linux box

Linux has SSH already. Copy your key across (`ssh-copy-id box`), add a `Host box` to `~/.ssh/config`, and on the box `sudo apt install python3-venv python3-dev patchelf`. Then in machines.vml:

```
@Machine box
Host=box
OS=linux
```

## Good to know

- **Awake?** Bob asks each machine as he opens a project: a card says *on a8: asleep?* if it doesn't answer. Wake it and pick the project again.
- **Windows Defender** scans everything a compiler writes, which slows a build several times over. Bob asks it to skip his build folders; that needs the build to run as an administrator, and is quietly skipped otherwise.
- **One at a time per machine**: a second build for a busy machine waits its turn.
