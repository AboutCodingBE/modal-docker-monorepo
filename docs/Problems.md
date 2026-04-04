# Summary of problems

## Tkinter not found
So the agent uses a native file picker. On the first startup, the health check was fine, but tkinter was not found: 

```text
Folder dialog error: No module named '_tkinter
```

it's a tkinter quirk. Tkinter is part of Python's standard library, so it's supposed to be included with Python. You can't 
install it via pip, which is why it's not in requirements.txt. The problem is that some Python installations — particularly 
on Linux — ship without the tkinter bindings. It depends on how Python was installed.

This is something we need to avoid when packaging the agent. 

Fixing this depends on the operating system: 

Ubuntu/Debian:
```bash
sudo apt install python3-tk
```

Fedora/RHEL:
```bash
sudo dnf install python3-tkinter
```

macOS (Homebrew):

```bash
brew install python-tk
```

After installing, restart your venv:

```bash
deactivate

source venv/bin/activate
```

Windows: It should be included by default. If not, reinstall Python and make sure "tcl/tk" is checked in the installer.

Tkinter will not work, at least not on Mac: 

```text
*** Assertion failure in -[NSMenu _setMenuName:], NSMenu.m:777
*** Terminating app due to uncaught exception 'NSInternalInconsistencyException', reason: 'NSWindow should only be instantiated on the main thread!'
libc++abi: terminating due to uncaught exception of type NSException
zsh: abort      python agent.py --dev
```

Going for a different solution.