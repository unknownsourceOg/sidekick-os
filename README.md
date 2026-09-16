# Sidekick OS

An animated desktop companion for computer help, coding, music and animation.
The desktop uses a dark green sci-fi theme. Open the companion to choose a task;
chat uses a free local model after its initial download.

## What this version does

- A persistent, draggable animated robot with idle, thinking, talking and alert
  states; click to open the hub or right-click for quick actions.
- Computer controls for files, network, sound, desktop settings and power options.
  A read-only diagnostic check can be passed into chat for an explanation.
- Separate local chat histories and prompts for computer help, coding, music and
  animation. Generated text is never automatically executed.
- Review and save code/replies. Existing regular files in your home folder receive
  backups before replacement; symbolic links and paths outside home are refused.
- A music workbench with standard MIDI sketches: separate chord, bass and drum
  tracks, a chosen key, tempo and style. Buttons open/install Audacity and LMMS.
- An animation workbench with a bundled four-second Blender project generator,
  Blender and Kdenlive buttons, and help writing animation scripts.
- A graphical AI setup page: RAM-based suggestions, selectable storage, download
  progress, pause/resume, pinned model revisions and SHA-256 verification.
- A local inference engine compiled from a pinned llama.cpp commit inside the ISO.
  First run downloads the chosen model rather than trying to locate an unpinned
  runtime release asset. The service listens on 127.0.0.1 only.
- Software installation uses a small fixed-action helper and the desktop's normal
  authorization dialog. It accepts only the listed software groups.

## Build and boot

Use **Actions → build sidekick os iso → Run workflow**. Builds produce an ISO,
SHA-256 file, diagnostic logs and a rendered desktop preview. The development
branch `sidekick/desktop-companion` builds amd64 on push. Main/tag/manual builds
retain both original architectures; development branch builds are not published
as Releases.

- **amd64:** Intel/AMD PCs and compatible Intel Macs. Choose EFI Boot, then
  **Live system (amd64)** to try the desktop. Hardware-specific drivers and firmware
  still need verification on the actual computer.
- **arm64:** the original generic ARM64 VM route remains available. This does not
  make a USB natively bootable on Apple Silicon.

Extract the ISO from its artifact ZIP before flashing it. Flashing replaces the
selected USB's contents. Save needed files before writing the new image.

The workflow verifies package prerequisites and native GUI startup before packing
an image. The amd64 image is then booted in a disposable QEMU VM with no writable
disk and no network. It must create the live user and keep XFCE, its window manager
and the companion running. The VM uses the image's kernel and initramfs directly;
this checks the live desktop startup path, not a physical machine's EFI firmware.

## First run

1. Open **AI Setup** in the hub.
2. Choose a storage folder on a drive where you keep files. A live USB's ordinary
   home folder may be temporary unless persistence is already active.
3. Choose a model and review its download size. Download & set up AI checks it,
   creates a user service and waits for a real ready response.
4. Use the creative pages to install/open the tools you need. The tools work
   independently of the model. Installation and model download require internet;
   installed tools and local inference can then run offline.

The former automatic USB partition script is not installed into this image. It
selected a partition too loosely to be a trustworthy guided storage operation.
This version uses a folder you select; it does not automatically create a
persistence partition or install over an existing disk.

## Model choices

| Model | Download | Suggested RAM |
|---|---:|---:|
| Qwen3-1.7B Q8 | about 1.8 GiB | 4 GB |
| Qwen3-4B Q4_K_M | about 2.3 GiB | 8 GB |
| Qwen3-8B Q4_K_M | about 4.7 GiB | 16 GB |

These are official Qwen GGUF models under Apache-2.0. Model hashes, sizes and
immutable revisions are in `mascot/models.json`. llama.cpp is MIT licensed; its
license and pinned source revision are included in the image. Debian applications
retain their own free-software licenses. There is no subscription or paid API in
the local chat path. Model quality and speed depend on hardware.

Sources: [Qwen models](https://huggingface.co/Qwen),
[llama.cpp](https://github.com/ggml-org/llama.cpp),
[Debian software packages](https://packages.debian.org/trixie/).

## Honest capability boundaries

Music chat can draft lyrics, arrangements and production instructions; the MIDI
generator produces an editable sketch. It does not produce a mastered recording.
Animation chat can plan and write scripts; Blender handles actual 3D projects and
rendering. The character's talking animation is visual; voice is not implemented.
The model does not see/hear other applications or intercept everything you do.
Supported buttons perform explicit actions; arbitrary autonomous app control,
model-written root commands and guaranteed correctness are not claimed.

`REQUIREMENTS.md` preserves the user's agreed goal so future work continues toward
the companion, not only an ISO or terminal assistant.

## Development checks

On a Debian/Ubuntu desktop with Python GI/Cairo, GTK3, mido, Xvfb and dbus-x11:

```sh
python3 -m unittest discover -s tests -v
xvfb-run -a dbus-run-session -- python3 mascot/sidekick_chat.py --smoke-test
```

For an existing Debian/Ubuntu XFCE installation, `sudo ./install.sh` installs the
companion and builds its engine. The complete live ISO is the main OS route.
