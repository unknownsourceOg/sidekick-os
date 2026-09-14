#!/usr/bin/env bash
# Build the Sidekick OS live ISO: bootable, installable, persistence-ready.
# Runs on any Debian/Ubuntu x86_64 or arm64 machine with root (GitHub Actions does this for us).
#   sudo ARCH=amd64 ./build-iso.sh      -> sidekick-os-amd64.iso   (Intel Mac, any PC)
#   sudo ARCH=arm64 ./build-iso.sh      -> sidekick-os-arm64.iso   (Apple Silicon in UTM)
set -euo pipefail
ARCH="${ARCH:-amd64}"
DIST="${DIST:-trixie}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${WORK:-/tmp/skos}"

command -v lb >/dev/null || { apt-get update -qq; apt-get install -y live-build debian-archive-keyring xorriso; }

rm -rf "$WORK"; mkdir -p "$WORK"; cd "$WORK"

M=http://deb.debian.org/debian/
S=http://security.debian.org/debian-security/

lb config \
  --mode debian \
  --distribution "$DIST" \
  --architectures "$ARCH" \
  --archive-areas "main contrib non-free non-free-firmware" \
  --mirror-bootstrap "$M" --parent-mirror-bootstrap "$M" \
  --mirror-chroot "$M" --parent-mirror-chroot "$M" \
  --mirror-binary "$M" --parent-mirror-binary "$M" \
  --mirror-chroot-security "$S" --parent-mirror-chroot-security "$S" \
  --mirror-binary-security "$S" --parent-mirror-binary-security "$S" \
  --compression xz \
  --binary-images iso-hybrid \
  --iso-application "Sidekick OS" \
  --iso-publisher "Sidekick" \
  --iso-volume "SIDEKICK" \
  --debian-installer live \
  --debian-installer-gui true \
  --memtest none \
  --apt-recommends false \
  --firmware-chroot true \
  --firmware-binary true \
  --bootappend-live "boot=live components quiet splash persistence persistence-encryption=none noeject username=hacker user-fullname=Sidekick hostname=sidekick"

# ---------- what goes in ----------
mkdir -p config/package-lists
cat > config/package-lists/sidekick.list.chroot <<'EOF'
xfce4
xfce4-terminal
xfce4-notifyd
lightdm
light-locker
network-manager-gnome
firefox-esr
thunar
mousepad
python3
python3-gi
python3-gi-cairo
gir1.2-gtk-3.0
python3-cairo
curl
wget
git
jq
tmux
htop
xclip
nano
gcc
make
python3-pip
python3-venv
samba
samba-common-bin
openssh-server
parted
dosfstools
fonts-jetbrains-mono
pulseaudio
pavucontrol
firmware-linux-free
live-boot
live-config
live-config-systemd
EOF
[ "$ARCH" = "amd64" ] && cat >> config/package-lists/sidekick.list.chroot <<'EOF'
firmware-iwlwifi
firmware-realtek
firmware-brcm80211
EOF

# ---------- files baked into the system ----------
INC=config/includes.chroot
mkdir -p "$INC"/opt/sidekick "$INC"/usr/local/bin "$INC"/etc/xdg/autostart \
         "$INC"/etc/profile.d "$INC"/etc/skel/.config/xfce4/xfconf/xfce-perchannel-xml \
         "$INC"/usr/share/applications "$INC"/etc/sudoers.d

cp "$REPO"/mascot/*.py "$INC"/opt/sidekick/
cp "$REPO"/theme/wallpaper.png "$INC"/opt/sidekick/
cp "$REPO"/ai/setup-ai.sh "$INC"/opt/sidekick/
cp "$REPO"/iso/sidekick-persist "$INC"/usr/local/bin/
cp "$REPO"/iso/sidekick-firstrun "$INC"/usr/local/bin/
chmod +x "$INC"/usr/local/bin/* "$INC"/opt/sidekick/setup-ai.sh

cat > "$INC"/opt/sidekick/sidekick-mascot <<'EOF'
#!/usr/bin/env bash
cd /opt/sidekick && exec python3 sidekick_chat.py
EOF
chmod +x "$INC"/opt/sidekick/sidekick-mascot
ln -sf /opt/sidekick/sidekick-mascot "$INC"/usr/local/bin/sidekick-mascot

# the companion starts with every desktop session
cat > "$INC"/etc/xdg/autostart/sidekick.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Sidekick companion
Exec=/opt/sidekick/sidekick-mascot
Icon=utilities-terminal
X-GNOME-Autostart-enabled=true
EOF
# first run: offer the model download, set up sharing
cat > "$INC"/etc/xdg/autostart/sidekick-firstrun.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Sidekick first run
Exec=xfce4-terminal --title="Sidekick setup" -e /usr/local/bin/sidekick-firstrun
X-GNOME-Autostart-enabled=true
EOF

# terminal brain: sk "question"
cat > "$INC"/usr/local/bin/sk <<'EOF'
#!/usr/bin/env bash
API=${SIDEKICK_API:-http://127.0.0.1:8080/v1/chat/completions}
q="$*"
[ -z "$q" ] && { echo 'usage: sk "your question"   (pipe too: cat err.log | sk explain)'; exit 1; }
[ -t 0 ] || q="$q"$'\n\n'"$(cat)"
sys='You are Sidekick in a terminal on Sidekick OS. Give the exact command or minimal code first, then one line of why. Be brief. Never invent flags.'
payload=$(jq -n --arg s "$sys" --arg q "$q" '{model:"local",stream:false,temperature:0.3,max_tokens:900,messages:[{role:"system",content:$s},{role:"user",content:$q}]}')
curl -s -m 600 -H 'Content-Type: application/json' -d "$payload" "$API" \
 | jq -r '.choices[0].message.content // "model not running - try: sidekick-ai start"' \
 | sed $'s/^/\033[38;5;48m/;s/$/\033[0m/'
EOF
chmod +x "$INC"/usr/local/bin/sk

cat > "$INC"/etc/profile.d/sidekick-banner.sh <<'EOF'
[ -n "$PS1" ] || return 0
printf '\033[38;5;48m'
cat <<'ART'
  ___ _____ ___  ___ _  _____ ___ _  _
 / __|_   _|   \| __| |/ / __| __| |/ /
 \__ \ | | | |) | _|| ' <| _|| _|| ' <
 |___/ |_| |___/|___|_|\_\___|___|_|\_\  os
ART
printf '\033[0m  model: '
curl -s -m 1 http://127.0.0.1:8080/health >/dev/null 2>&1 \
  && printf '\033[38;5;48monline\033[0m' || printf '\033[38;5;214mstopped -> sidekick-ai start\033[0m'
printf '   ask: \033[38;5;51msk "how do I ..."\033[0m   persistence: \033[38;5;51msudo sidekick-persist\033[0m\n\n'
EOF

# xfce look: dark, our wallpaper, jetbrains mono terminal
cat > "$INC"/etc/skel/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-desktop.xml <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfce4-desktop" version="1.0">
  <property name="backdrop" type="empty">
    <property name="screen0" type="empty">
      <property name="monitor0" type="empty">
        <property name="workspace0" type="empty">
          <property name="last-image" type="string" value="/opt/sidekick/wallpaper.png"/>
          <property name="image-style" type="int" value="5"/>
        </property>
      </property>
    </property>
  </property>
</channel>
EOF
cat > "$INC"/etc/skel/.config/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xsettings" version="1.0">
  <property name="Net" type="empty">
    <property name="ThemeName" type="string" value="Adwaita-dark"/>
    <property name="IconThemeName" type="string" value="Adwaita"/>
  </property>
  <property name="Gtk" type="empty">
    <property name="FontName" type="string" value="Sans 10"/>
    <property name="MonospaceFontName" type="string" value="JetBrains Mono 11"/>
  </property>
</channel>
EOF
mkdir -p "$INC"/etc/skel/.config/xfce4/terminal
cat > "$INC"/etc/skel/.config/xfce4/terminal/terminalrc <<'EOF'
[Configuration]
ColorForeground=#a8f0cf
ColorBackground=#060a0e
ColorCursor=#4ade9b
FontName=JetBrains Mono 11
MiscAlwaysShowTabs=FALSE
ScrollingUnlimited=TRUE
BackgroundMode=TRANSPARENT
BackgroundDarkness=0.92
EOF

# passwordless sudo for the live user (it is a live system; the installer sets a real password)
echo "hacker ALL=(ALL) NOPASSWD: ALL" > "$INC"/etc/sudoers.d/sidekick
chmod 440 "$INC"/etc/sudoers.d/sidekick

# ---------- hooks ----------
mkdir -p config/hooks/normal
cat > config/hooks/normal/0100-sidekick.hook.chroot <<'EOF'
#!/bin/sh
set -e
systemctl enable ssh 2>/dev/null || true
systemctl enable smbd 2>/dev/null || true
systemctl set-default graphical.target
# samba share of ~/Shared for the Mac
cat >> /etc/samba/smb.conf <<'SMB'

[sidekick]
   comment = Sidekick shared folder
   path = /home/hacker/Shared
   browseable = yes
   read only = no
   valid users = hacker
   create mask = 0664
   directory mask = 0775
SMB
mkdir -p /etc/skel/Shared
# never let a live system look like it phones home
rm -f /etc/apt/apt.conf.d/20auto-upgrades 2>/dev/null || true
EOF
chmod +x config/hooks/normal/0100-sidekick.hook.chroot

# ---------- build ----------
lb build 2>&1 | tail -40
iso=$(ls -1 live-image-*.hybrid.iso live-image-*.iso 2>/dev/null | head -1)
[ -n "$iso" ] || { echo "BUILD FAILED: no iso produced"; exit 1; }
out="$REPO/sidekick-os-$ARCH.iso"
mv "$iso" "$out"
ls -lh "$out"
sha256sum "$out" | tee "$out.sha256"
