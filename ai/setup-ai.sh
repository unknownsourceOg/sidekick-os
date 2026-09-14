#!/usr/bin/env bash
# Install the local coding model: llama.cpp + Qwen2.5-Coder sized to this machine's RAM.
# Free, offline after the first download, nothing sent anywhere.
set -euo pipefail
SK="${SIDEKICK_HOME:-$HOME/.sidekick}"
BIN="$SK/bin"; MODELS="$SK/models"
mkdir -p "$BIN" "$MODELS"

arch=$(uname -m)
case "$arch" in
  x86_64) want="bin-ubuntu-x64.tar.gz" ;;
  aarch64|arm64) want="bin-ubuntu-arm64.tar.gz" ;;
  *) echo "unsupported arch $arch"; exit 1 ;;
esac

if [ ! -x "$BIN/llama-server" ]; then
  echo ">> fetching llama.cpp ($arch)"
  url=$(curl -sL "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=1" \
        | grep -o "https://[^\"]*$want" | head -1)
  [ -n "$url" ] || { echo "could not resolve llama.cpp release"; exit 1; }
  curl -L --progress-bar -o /tmp/llama.tar.gz "$url"
  tar -xzf /tmp/llama.tar.gz -C /tmp
  find /tmp -maxdepth 3 -type f \( -name 'llama-server' -o -name 'libggml*.so*' -o -name 'libllama*.so*' \
       -o -name 'libmtmd*.so*' \) -exec cp {} "$BIN/" \;
  chmod +x "$BIN"/llama-server
  rm -f /tmp/llama.tar.gz
fi

# pick the biggest model this machine can actually run
ram=$(awk '/MemTotal/{printf "%d", $2/1024/1024}' /proc/meminfo)
if   [ "$ram" -ge 30 ]; then name="Qwen2.5-Coder-14B-Instruct-Q4_K_M.gguf"; repo="Qwen2.5-Coder-14B-Instruct-GGUF"; ctx=16384
elif [ "$ram" -ge 15 ]; then name="Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf";  repo="Qwen2.5-Coder-7B-Instruct-GGUF";  ctx=16384
elif [ "$ram" -ge 7 ];  then name="Qwen2.5-Coder-3B-Instruct-Q4_K_M.gguf";  repo="Qwen2.5-Coder-3B-Instruct-GGUF";  ctx=8192
else                         name="Qwen2.5-Coder-1.5B-Instruct-Q4_K_M.gguf";repo="Qwen2.5-Coder-1.5B-Instruct-GGUF";ctx=4096
fi
echo ">> ${ram} GB RAM detected -> $name"

if [ ! -f "$MODELS/$name" ]; then
  echo ">> downloading the model once (this is the big one, then you are offline forever)"
  curl -L --progress-bar -o "$MODELS/$name.part" \
    "https://huggingface.co/bartowski/$repo/resolve/main/$name"
  mv "$MODELS/$name.part" "$MODELS/$name"
fi

cat > "$SK/model.env" <<EOF
MODEL_PATH=$MODELS/$name
CTX=$ctx
THREADS=$(nproc)
EOF

# user service: starts with the desktop, restarts if it dies, no root needed
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/sidekick-ai.service" <<EOF
[Unit]
Description=Sidekick local coding model (llama.cpp)
[Service]
EnvironmentFile=$SK/model.env
ExecStart=$BIN/llama-server -m \${MODEL_PATH} -c \${CTX} -t \${THREADS} \\
          --host 127.0.0.1 --port 8080 --no-webui --metrics
Restart=always
RestartSec=3
Nice=5
[Install]
WantedBy=default.target
EOF

cat > "$BIN/sidekick-ai" <<'EOF'
#!/usr/bin/env bash
# sidekick-ai start|stop|status|log|swap
case "${1:-status}" in
  start)  systemctl --user start sidekick-ai && echo "model starting on 127.0.0.1:8080" ;;
  stop)   systemctl --user stop sidekick-ai ;;
  status) systemctl --user --no-pager status sidekick-ai | head -12
          curl -s -m 2 http://127.0.0.1:8080/health && echo || echo "not answering yet" ;;
  log)    journalctl --user -u sidekick-ai -f ;;
  swap)   ${EDITOR:-nano} "$HOME/.sidekick/model.env" && systemctl --user restart sidekick-ai ;;
  *)      echo "usage: sidekick-ai start|stop|status|log|swap" ;;
esac
EOF
chmod +x "$BIN/sidekick-ai"

systemctl --user daemon-reload 2>/dev/null || true
systemctl --user enable --now sidekick-ai 2>/dev/null || "$BIN/sidekick-ai" start || true
echo ">> local model ready: http://127.0.0.1:8080  (sidekick-ai status)"
