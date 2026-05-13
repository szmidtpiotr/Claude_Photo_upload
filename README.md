# 📸 Claude Photo Upload

A lightweight screenshot upload server that runs on your local machine. Upload images from any browser (including iPhone), save them to `~/screenshots/`, and get the file path copied to your clipboard — ready to paste into Claude.

## Features

- Paste from clipboard (Ctrl+V / long-press on iOS)
- Choose file from disk or camera roll
- Image preview before sending
- Auto-copies saved path to clipboard
- Recent uploads list
- Daily auto-cleanup (removes screenshots older than 2 days)
- Runs as a systemd user service (starts automatically on login)

## Install

Run this on the target machine (requires Python 3 and systemd):

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/szmidtpiotr/Claude_Photo_upload/main/install.sh)
```

The server will start immediately and auto-start on every login. Screenshots are saved to `~/screenshots/`.

## Access

Open in any browser on your local network:

```
http://<machine-ip>:37701
```

## Manage the service

```bash
# Check status
systemctl --user status screenshot-upload.service

# Stop
systemctl --user stop screenshot-upload.service

# Start
systemctl --user start screenshot-upload.service

# Restart
systemctl --user restart screenshot-upload.service

# Start manually (without systemd)
python3 ~/.local/share/screenshot-upload/server.py
```

## Files

| Path | Description |
|---|---|
| `~/.local/share/screenshot-upload/server.py` | The server |
| `~/.config/systemd/user/screenshot-upload.service` | Systemd service |
| `~/.config/systemd/user/screenshot-cleanup.timer` | Daily cleanup timer |
| `~/screenshots/` | Where uploads are saved |
