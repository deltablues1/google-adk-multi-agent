#!/bin/sh
# Wall panel: Chromium showing the Jarvis dashboard, nothing else.
#
# Lives in the user's home and is started from ~/.config/labwc/autostart, so it
# needs no root and is undone by deleting one file.
#
# The profile is its own directory rather than the default one: the panel stays
# logged into Home Assistant across reboots without entangling that session with
# any browsing done on this Pi by hand.

URL="${PANEL_URL:-http://192.168.100.200:8123/jarvis-dom/pregled}"
PROFILE="$HOME/.config/chromium-panel"

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"

# Chromium refuses to start again if it thinks it crashed, and a wall panel
# cannot answer a dialogue. Clearing these two makes the restart silent.
if [ -d "$PROFILE/Default" ]; then
    sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/' \
        "$PROFILE/Default/Preferences" 2>/dev/null || true
fi

# Only ever one panel browser.
pkill -f "user-data-dir=$PROFILE" 2>/dev/null
sleep 2

exec /usr/bin/chromium \
    --ozone-platform=wayland \
    --enable-wayland-ime \
    --kiosk \
    --user-data-dir="$PROFILE" \
    --password-store=basic \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-features=Translate,TranslateUI \
    --check-for-update-interval=31536000 \
    --overscroll-history-navigation=0 \
    --disable-pinch \
    --autoplay-policy=no-user-gesture-required \
    "$URL"
