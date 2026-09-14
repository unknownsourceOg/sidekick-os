#!/usr/bin/env bash
# Turn a plain Debian/Ubuntu/Arch system - live USB or installed - into Sidekick OS:
# animated companion on top of every window, local coding model, sci-fi theme, file sharing.
# Safe to re-run. Nothing here phones home.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SK=/opt/sidekick
USER_NAME="${SUDO_USER:-$USER}"
USER_HOME=$(getent passwd "$USER_NAME" | cut -d: -f6)

banner() { printf '\n\033[38;5;48m[ %s ]\033[0m\n' "$1"; }
need_root() { [ "$(id -u)" = 0 ] || { echo "run with sudo: sudo $0"; exit 1; }; }
need_root

banner "1/6  packages"
if command -v apt-get >/dev/null; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq || true
  apt-get install -y --no-install-recommends \
    python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0 python3-cairo \
    curl ca-certificates git tmux htop jq xclip fonts-jetbrains-mono \
    samba samba-common-bin openssh-server feh x11-xserver-utils || true
elif command -v pacman >/dev/null; then
  pacman -Sy --noconfirm --needed python python-gobject python-cairo gtk3 curl git \
    tmux htop jq xclip ttf-jetbrains-mono samba openssh feh xorg-xrandr || true
else
  echo "!! unknown package manager - install python3-gi, gtk3, curl, samba yourself"
fi

banner "2/6  companion"
install -d "$SK"
cp -f "$HERE"/mascot/*.py "$SK"/
cp -f "$HERE"/theme/wallpaper.png "$SK"/ 2>/dev/null || true
cat > "$SK/sidekick-mascot" <<EOF
#!/usr/bin/env bash
cd $SK && exec python3 sidekick_chat.py
EOF
chmod +x "$SK/sidekick-mascot"
ln -sf "$SK/sidekick-mascot" /usr/local/bin/sidekick-mascot

install -d /etc/xdg/autostart
cat > /etc/xdg/autostart/sidekick.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Sidekick companion
Exec=$SK/sidekick-mascot
Icon=utilities-terminal
X-GNOME-Autostart-enabled=true
NoDisplay=false
EOF
cp -f /etc/xdg/autostart/sidekick.desktop /usr/share/applications/sidekick.desktop

banner "3/6  terminal brain (sk)"
cat > /usr/local/bin/sk <<'EOF'
#!/usr/bin/env bash
# sk "how do I find the 10 biggest files here?"   -> answer from the local model, in the terminal
API=${SIDEKICK_API:-http://127.0.0.1:8080/v1/chat/completions}
q="$*"
[ -z "$q" ] && { echo 'usage: sk "your question"   (or pipe: cat err.log | sk explain)'; exit 1; }
if [ ! -t 0 ]; then q="$q"$'\n\n'"$(cat)"; fi
sys='You are Sidekick in a terminal. Answer with the exact command or minimal code first, then one line of why. Be brief. Never invent flags.'
payload=$(jq -n --arg s "$sys" --arg q "$q" \
  '{model:"local",stream:false,temperature:0.3,max_tokens:900,
    messages:[{role:"system",content:$s},{role:"user",content:$q}]}')
out=$(curl -s -m 600 -H 'Content-Type: application/json' -d "$payload" "$API" \
      | jq -r '.choices[0].message.content // "no answer"')
printf '\033[38;5;48m%s\033[0m\n' "$out"
EOF
chmod +x /usr/local/bin/sk

banner "4/6  sci-fi theme"
install -d /etc/skel/.config
cat > /etc/profile.d/sidekick-banner.sh <<'EOF'
[ -n "$PS1" ] || return 0
printf '\033[38;5;48m'
cat <<'ART'
  ___ _____ ___  ___ _  _____ ___ _  _
 / __|_   _|   \| __| |/ / __| __| |/ /
 \__ \ | | | |) | _|| ' <| _|| _|| ' <
 |___/ |_| |___/|___|_|\_\___|___|_|\_\   os
ART
printf '\033[0m  local model: '
curl -s -m 1 http://127.0.0.1:8080/health >/dev/null && printf '\033[38;5;48monline\033[0m' || printf '\033[38;5;214mstopped (sidekick-ai start)\033[0m'
printf '\n  ask anything:  \033[38;5;51msk "how do I ..."\033[0m   |  companion: click the orb\n\n'
EOF
# dark, high-contrast, green-on-black defaults everywhere we can reach
cat > /etc/inputrc.sidekick <<'EOF'
set colored-stats on
set colored-completion-prefix on
EOF
grep -q inputrc.sidekick /etc/inputrc 2>/dev/null || echo '$include /etc/inputrc.sidekick' >> /etc/inputrc
if [ -f "$SK/wallpaper.png" ]; then
  su - "$USER_NAME" -c "gsettings set org.gnome.desktop.background picture-uri 'file://$SK/wallpaper.png'" 2>/dev/null || true
  su - "$USER_NAME" -c "gsettings set org.gnome.desktop.background picture-uri-dark 'file://$SK/wallpaper.png'" 2>/dev/null || true
  su - "$USER_NAME" -c "xfconf-query -c xfce4-desktop -p /backdrop/screen0/monitor0/workspace0/last-image -s $SK/wallpaper.png" 2>/dev/null || true
fi

banner "5/6  file sharing with your Mac"
install -d -m 0775 -o "$USER_NAME" -g "$USER_NAME" "$USER_HOME/Shared"
if [ -f /etc/samba/smb.conf ] && ! grep -q '\[sidekick\]' /etc/samba/smb.conf; then
  cat >> /etc/samba/smb.conf <<EOF

[sidekick]
   comment = Sidekick shared folder
   path = $USER_HOME/Shared
   browseable = yes
   read only = no
   valid users = $USER_NAME
   create mask = 0664
   directory mask = 0775
EOF
fi
systemctl enable --now smbd 2>/dev/null || true
systemctl enable --now ssh 2>/dev/null || systemctl enable --now sshd 2>/dev/null || true
echo "   set the share password now (used from macOS Finder):"
smbpasswd -a "$USER_NAME" || true

banner "6/6  local coding model"
su - "$USER_NAME" -c "bash $HERE/ai/setup-ai.sh" || echo "!! model setup failed - run ai/setup-ai.sh as $USER_NAME"

ip=$(hostname -I 2>/dev/null | awk '{print $1}')
cat <<EOF

\033[38;5;48mSidekick OS is installed.\033[0m
  companion   : starts with the desktop, or run  sidekick-mascot
  terminal ai : sk "write a bash loop that resizes every png here"
  model       : sidekick-ai status | start | stop | log
  from macOS  : Finder > Go > Connect to Server >  smb://$ip/sidekick   (user $USER_NAME)
                terminal:  ssh $USER_NAME@$ip
Log out and back in so the companion and the banner load.
EOF
