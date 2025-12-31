# Quick Start: GUI Development with Auto-Reload

## 🎯 Your Immediate Next Steps (In Docker)

### 1️⃣ Inside Your Docker Container - Install Dependencies

```bash
cd /development/gui/gui_dev/
pip3 install -r requirements-gui.txt
```

### 2️⃣ Check Your Display Setup

Your container needs the `DISPLAY` environment variable. Check if it's set:

```bash
echo $DISPLAY
```

**If empty**, you need to restart your Docker container with X11 forwarding (see below).

**If set** (e.g., `host.docker.internal:0`), you're good to go!

### 3️⃣ Run Development Mode

```bash
./dev.sh
```

Now when you edit any `.py` file in `GUI/` and save it, the GUI will automatically restart with your changes! 🎉

---

## 📝 Development Workflow

1. **Start dev mode once** (inside container):
   ```bash
   cd /development/gui && ./dev.sh
   ```

2. **Edit files** (on your host machine using your favorite editor)

3. **Save** - The GUI automatically restarts!

4. **Stop** - Press `Ctrl+C` in the terminal running `dev.sh`
