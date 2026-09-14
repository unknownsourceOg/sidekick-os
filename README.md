# Sidekick OS

A live-bootable Linux where the AI is part of the system: an animated companion on top of
every window, a coding model running locally, a sci-fi terminal-first desktop, install-to-disk,
USB persistence and file sharing back to macOS. No accounts, no telemetry, all free.

```
sidekickos/
  install.sh              turn ANY running Debian/Ubuntu/Arch (live USB or installed) into Sidekick OS
  mascot/                 the companion: GTK3 + Cairo animated orb, chat window, "explain what I highlighted"
  ai/setup-ai.sh          llama.cpp + Qwen2.5-Coder sized to the machine's RAM, as a user service
  theme/wallpaper.png     generated sci-fi wallpaper
  iso/build-iso.sh        live-build recipe -> bootable, installable ISO (amd64 + arm64)
  iso/sidekick-persist    makes the free space on the USB stick permanent storage
  iso/sidekick-firstrun   first-boot walkthrough + optional model download
  .github/workflows/      builds both ISOs on GitHub's free runners and publishes a Release
```

## Two ways to get it

**A. No GitHub needed.** Flash a stock Debian 13 live ISO to a USB, boot it, then:
```
git clone <this repo> && cd sidekickos && sudo ./install.sh
```

**B. A real Sidekick OS ISO.** Push this folder to a GitHub repo and run the
`build sidekick os iso` workflow (Actions tab -> Run workflow). ~40 min later a Release
appears with `sidekick-os-amd64.iso` and `sidekick-os-arm64.iso`.

## Mac reality check
- **Intel Mac**: boots the amd64 ISO from USB. Hold Option at power-on, pick *EFI Boot*.
  T2 models (2018-2020) need an external USB keyboard/mouse and usually USB tethering for
  internet, because the T2 input and wifi drivers are not in the mainline kernel.
- **Apple Silicon (M1-M4)**: cannot boot an x86 USB at all. Run the arm64 ISO in
  [UTM](https://mac.getutm.app) (free) - full desktop, persistence and sharing, no risk to macOS.

## Model sizing (chosen automatically by RAM)
| RAM | model | download |
|---|---|---|
| 32 GB+ | Qwen2.5-Coder 14B Q4 | ~9 GB |
| 16 GB | Qwen2.5-Coder 7B Q4 | ~4.7 GB |
| 8 GB | Qwen2.5-Coder 3B Q4 | ~2 GB |
| <8 GB | Qwen2.5-Coder 1.5B Q4 | ~1 GB |

CPU-only speed is roughly 3-9 tokens/sec for 7B on a modern laptop: fine for commands,
explanations and small files; slow for large refactors. The model is not in the ISO - it is
downloaded once on first run so the ISO stays under GitHub's 2 GB release limit.

## Status
Written but never executed: this workspace has no X server and no x86 build tools, so the
ISO build and the GTK companion have not been run yet. The GitHub workflow is the test.
