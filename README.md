# VML (Visualised Markup Language)

**A revolutionary cross-platform RAD IDE that designs itself**

VML is a lightweight, patent-pending application development system combining simple markup with multi-language scripting (Lua, C#, Bash, Python) to create desktop applications with unprecedented simplicity.

## What Makes VML Unique

### The Parent= Innovation
Unlike traditional nested UI markup (XML, XAML, HTML), VML uses a **flat structure with named parent references**:
```vml
@Window MainWindow
Title=My Application
Width=800
Height=600

@StackPanel Container
Parent=MainWindow
Margin=20

@Button SaveBtn
Parent=Container
Content=Save
OnClick=SaveScript

@Script SaveScript
Interpreter=lua
-- Your code here
Vml("InfoDialog", "Saved!")
```

**Advantages:**
- No closing tags or nesting hell
- Grep/sed/awk friendly (200-line parser!)
- Easy refactoring - change one Parent= line
- Order independent
- Human readable, machine parseable

### Architecture
```
VML File (.vml)
    ↓
AWK Parser (3KB!)
    ↓
SQLite Database
    ↓
.NET Reflection Runtime
    ↓
Avalonia UI + Multi-interpreter Scripts
```

**Key Components:**

1. **vml-parse** - 200-line AWK script converts .vml → SQL
2. **SQLite Database** - stores UI tree, properties, scripts, events
3. **Reflection Engine** - dynamically creates controls from database
4. **Event System** - soft-coded via control_events table
5. **Multi-interpreter** - Lua, C#, Bash, Python with named persistent sessions
6. **Self-hosting** - the designer itself is built in VML

### Supported Interpreters

- **Lua** - Lightweight, embedded, perfect for game logic
- **C#** - Full .NET access via Roslyn scripting
- **Bash/PowerShell** - System automation
- **Python** - Coming soon

**Named instances** allow scripts to maintain state:
```vml
@Script InitGame
Interpreter=lua mygame
player_health = 100

@Script DamagePlayer
Interpreter=lua mygame
player_health = player_health - 10
```

### Control Events

Events are defined in database, not hardcoded:
```vml
@Button MyButton
OnClick=MyScript
OnPointerEnter=HoverScript
OnLostFocus=ValidateScript
```

Supported events: Click, TextChanged, SelectionChanged, GotFocus, LostFocus, PointerEnter, PointerLeave, KeyDown, and more.

## Installation

### Linux (Ubuntu/Debian)
```bash
# Install .NET 8
wget https://dot.net/v1/dotnet-install.sh
bash dotnet-install.sh --channel 8.0

# Clone and build
git clone https://github.com/wallisoft/vml.git
cd vml
dotnet build
dotnet run
```

### Windows 11
```bash
# Install .NET 8 from https://dotnet.microsoft.com/download

# Clone and build
git clone https://github.com/wallisoft/vml.git
cd vml
dotnet build
dotnet run
```

### Android
*Coming soon*

## Quick Start

Create `hello.vml`:
```vml
@Window HelloWindow
Title=Hello VML
Width=400
Height=300

@StackPanel Main
Parent=HelloWindow
Margin=20
Spacing=10

@TextBlock Greeting
Parent=Main
Text=Hello, World!
FontSize=24

@Button ClickMe
Parent=Main
Content=Click Me
OnClick=GreetScript

@Script GreetScript
Interpreter=lua
Vml("InfoDialog", "Hello from VML!")
```

Run:
```bash
vml-parse hello.vml | sqlite3 ~/.vml/vml.db
dotnet run
```

## Available VML Functions

### Lua/C# Scripts
```lua
-- Dialogs
Vml("InfoDialog", "message")
Vml("ErrorDialog", "error")
result = Vml("ConfirmDialog", "question?")
text = Vml("InputDialog", "prompt", "default")
file = Vml("FileOpenDialog", "title", "filter")

-- Properties
value = Vml("GetProperty", "ControlName", "PropertyName")
Vml("SetProperty", "ControlName", "PropertyName", value)

-- Database
results = Vml("SqlQuery", "SELECT * FROM table")
Vml("SqlExecute", "UPDATE table SET x=1")

-- Forms
Vml("FormOpen", "other-form.vml")
Vml("FormOpenModal", "dialog.vml")

-- System
Vml("Shell", "ls -la")
Vml("AppExit")

-- Settings
value = Vml("GetSetting", "key")
Vml("SetSetting", "key", "value")
```

## Project Structure
```
vml/
├── VB.csproj              # Project file
├── vml-parse              # AWK parser (the magic!)
├── Program.cs             # Entry point
├── FormLoader.cs          # Runtime form loader + event wiring
├── DesignerWindow.cs      # Design-time canvas
├── VmlLuaEngine.cs        # Lua interpreter integration
├── ScriptHandler.cs       # Multi-interpreter executor
├── PropertyStore.cs       # Database initialization
└── vml/                   # VML forms
    ├── designer.vml       # The IDE itself!
    ├── script-editor.vml  # Script editor
    ├── about_dialog.vml   # About dialog
    └── ...
```

## The Self-Hosting Magic

The designer that creates VML apps is **itself built in VML**. The `designer.vml` file defines the IDE's UI, menus, canvas, properties panel - all parsed by the same system it creates apps with. This recursive, self-hosting design is part of what makes VML unique.

## License

**Dual License:**

### Open Source (MIT License)
Free for personal, educational, and open source projects.

### Commercial License
Required for commercial/proprietary applications. Contact: wallisoft@gmail.com

**UK Patent Applications Filed** - VML markup language and system architecture are patent-pending in the United Kingdom.

## Roadmap

- [ ] Android support (Q1 2025)
- [ ] Python interpreter integration
- [ ] WebAssembly scripting
- [ ] Visual theme designer
- [ ] Plugin system
- [ ] Package manager for VML components
- [ ] VS Code extension

## Contributing

We welcome contributions! Please read CONTRIBUTING.md first.

Areas needing help:
- Documentation and tutorials
- Example applications
- Bug reports and testing
- Platform-specific installers

## Credits

**Created by:** Steve Wallis (Wallisoft)  
**AI Assistant:** Claude (Anthropic)  
**Year:** 2024-2025

## Contact

- Email: wallisoft@gmail.com
- GitHub: https://github.com/wallisoft/vml

---

*VML - Write less code, build more apps*
