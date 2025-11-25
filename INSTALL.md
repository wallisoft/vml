# Installation

## Quick Install

**Download and run:**
```bash
curl -O https://raw.githubusercontent.com/wallisoft/visualised/main/stub.sh
curl -O https://raw.githubusercontent.com/wallisoft/visualised/main/seed.db
chmod +x stub.sh
./stub.sh
```

This will:
1. Clone the repository
2. Build VB
3. Install to `~/.local/bin/VB`
4. Setup database at `~/.visualised/visualised.db`
5. Add to PATH

**System-wide install (requires sudo):**
```bash
sudo ./stub.sh --system
```

Installs to:
- Binary: `/usr/local/bin/VB`
- Database: `/var/lib/visualised/visualised.db`
- VML: `/usr/local/share/visualised/vml/`

## Manual Build

```bash
git clone https://github.com/wallisoft/visualised
cd visualised
dotnet build -c Release
./bin/Release/net9.0/VB
```

## Dependencies

- .NET 9 SDK
- SQLite (included via NuGet)
- Avalonia (included via NuGet)

## Uninstall

**User install:**
```bash
rm -rf ~/.local/bin/VB ~/.local/share/visualised ~/.visualised
# Remove from ~/.bashrc: export PATH="$PATH:$HOME/.local/bin"
```

**System install:**
```bash
sudo rm -rf /usr/local/bin/VB /usr/local/share/visualised /var/lib/visualised
```

## Database Locations

VB detects install type at runtime:

- **System install** (`/usr/*`, `/opt/*`): `/var/lib/visualised/visualised.db`
- **User install** (anywhere else): `~/.visualised/visualised.db`

The seed database provides schema. Runtime state persists across sessions.
