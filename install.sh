#!/usr/bin/env bash
# Install the companion into an existing Debian/Ubuntu XFCE desktop.
# The live ISO remains the complete OS route.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo 'Run this installer as administrator.' >&2; exit 1; }
command -v apt-get >/dev/null || { echo 'This installer supports Debian/Ubuntu desktops.' >&2; exit 1; }
HERE=$(cd "$(dirname "$0")" && pwd)
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  python3 python3-gi python3-gi-cairo python3-cairo gir1.2-gtk-3.0 \
  xorg xserver-xorg-input-libinput xfce4 xfce4-terminal lightdm lightdm-gtk-greeter \
  dbus-user-session dbus-x11 pkexec mate-polkit geany fonts-jetbrains-mono \
  thunar mousepad pavucontrol network-manager-gnome wpasupplicant git cmake build-essential libssl-dev
install -d /opt/sidekick /opt/sidekick/templates /usr/local/libexec /usr/share/polkit-1/actions /etc/xdg/autostart
install -m 644 "$HERE"/mascot/*.py "$HERE"/mascot/models.json /opt/sidekick/
install -m 644 "$HERE"/mascot/templates/*.py /opt/sidekick/templates/
install -m 644 "$HERE"/theme/wallpaper.png /opt/sidekick/
install -m 755 "$HERE"/system/sidekick-admin /usr/local/libexec/
install -m 644 "$HERE"/system/org.sidekick.install-tools.policy /usr/share/polkit-1/actions/
install -m 644 "$HERE"/system/polkit-mate-authentication-agent-1.desktop /etc/xdg/autostart/
cat > /opt/sidekick/sidekick-mascot <<'EOF'
#!/bin/sh
exec /usr/bin/python3 /opt/sidekick/sidekick_chat.py "$@"
EOF
chmod 755 /opt/sidekick/sidekick-mascot
ln -sf /opt/sidekick/sidekick-mascot /usr/local/bin/sidekick-mascot
cat > /usr/share/applications/sidekick.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Sidekick
Exec=/opt/sidekick/sidekick-mascot
Icon=face-smile
Categories=Utility;Development;AudioVideo;
Terminal=false
EOF
sed 's|Exec=/opt/sidekick/sidekick-mascot$|Exec=/opt/sidekick/sidekick-mascot --background|' \
  /usr/share/applications/sidekick.desktop > /etc/xdg/autostart/sidekick.desktop
bash "$HERE/ai/build-engine.sh"
printf '%s\n' 'Installed. Open Sidekick from the Applications menu as your normal desktop user.'
