#!/usr/bin/env python3
"""Chat window + local model client + the app glue. Started by sidekick-mascot."""
import gi, json, os, subprocess, threading, urllib.request, urllib.error
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib
from sidekick_mascot import Mascot, API, MODEL, PERSONA, IDLE, THINK, TALK, ALERT

CSS = b"""
window.sk { background: rgba(8,12,16,0.96); }
textview.sk, textview.sk text { background: transparent; color: #d8e6f2;
  font-family: "JetBrains Mono","DejaVu Sans Mono",monospace; font-size: 13px; }
entry.sk { background: #0e1620; color: #e8f2ff; border: 1px solid #1f3a4d;
  border-radius: 10px; padding: 9px 12px; caret-color: #4ade9b; }
label.sk { color: #4ade9b; font-family: monospace; font-size: 11px; }
label.dim { color: #6f8298; font-family: monospace; font-size: 11px; }
button.sk { background: #10202c; color: #bfe6d4; border: 1px solid #1f3a4d; border-radius: 10px; }
"""


class Chat(Gtk.Window):
    def __init__(self, app):
        super().__init__(title="sidekick://chat")
        self.app = app
        self.set_default_size(560, 480)
        self.set_keep_above(True)
        self.get_style_context().add_class("sk")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_start(12); box.set_margin_end(12)
        box.set_margin_top(10); box.set_margin_bottom(12)

        self.head = Gtk.Label(label="[ sidekick ] local model — nothing leaves this machine")
        self.head.get_style_context().add_class("sk")
        self.head.set_xalign(0)
        box.pack_start(self.head, False, False, 0)

        sw = Gtk.ScrolledWindow()
        self.view = Gtk.TextView()
        self.view.get_style_context().add_class("sk")
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.set_editable(False)
        self.buf = self.view.get_buffer()
        sw.add(self.view)
        box.pack_start(sw, True, True, 0)

        row = Gtk.Box(spacing=8)
        self.entry = Gtk.Entry()
        self.entry.get_style_context().add_class("sk")
        self.entry.set_placeholder_text("ask, or paste an error")
        self.entry.connect("activate", lambda *_: self.send())
        row.pack_start(self.entry, True, True, 0)
        b = Gtk.Button(label="run")
        b.get_style_context().add_class("sk")
        b.connect("clicked", lambda *_: self.send())
        row.pack_start(b, False, False, 0)
        box.pack_start(row, False, False, 0)
        self.add(box)
        self.connect("delete-event", self.hide_on_close)
        self.say("sidekick", "Online. Ask me anything, or highlight text anywhere and right-click me "
                             "to have it explained.\nTry: 'write a python script that renames photos by date'")

    def hide_on_close(self, *_):
        self.hide()
        return True

    def say(self, who, text):
        tag = "you > " if who == "you" else "sk  > "
        self.buf.insert(self.buf.get_end_iter(), f"\n{tag}{text}\n")
        GLib.idle_add(self.scroll)

    def append(self, chunk):
        self.buf.insert(self.buf.get_end_iter(), chunk)
        self.scroll()

    def scroll(self):
        self.view.scroll_to_iter(self.buf.get_end_iter(), 0, False, 0, 1)
        return False

    def send(self, text=None):
        q = (text or self.entry.get_text()).strip()
        if not q:
            return
        self.entry.set_text("")
        self.say("you", q)
        self.app.mascot.set_mood(THINK)
        self.buf.insert(self.buf.get_end_iter(), "\nsk  > ")
        threading.Thread(target=self.stream, args=(q,), daemon=True).start()

    def stream(self, q):
        self.app.turns.append({"role": "user", "content": q})
        body = json.dumps({
            "model": MODEL,
            "messages": [{"role": "system", "content": PERSONA}] + self.app.turns[-12:],
            "stream": True, "temperature": 0.4, "max_tokens": 1200,
        }).encode()
        req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
        got = []
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                GLib.idle_add(self.app.mascot.set_mood, TALK)
                for raw in r:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        d = json.loads(data)["choices"][0]["delta"].get("content", "")
                    except Exception:
                        continue
                    if d:
                        got.append(d)
                        GLib.idle_add(self.append, d)
        except urllib.error.URLError as e:
            GLib.idle_add(self.append,
                          f"[no model answering on {API}]\n"
                          f"  reason: {e}\n"
                          f"  fix:    sidekick-ai start      (or: systemctl --user restart sidekick-ai)\n")
            GLib.idle_add(self.app.mascot.set_mood, ALERT)
        except Exception as e:
            GLib.idle_add(self.append, f"[error] {e}\n")
            GLib.idle_add(self.app.mascot.set_mood, ALERT)
        if got:
            self.app.turns.append({"role": "assistant", "content": "".join(got)})
        GLib.idle_add(self.append, "\n")
        GLib.timeout_add(2500, lambda: self.app.mascot.set_mood(IDLE) or False)


class App:
    def __init__(self):
        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.turns = []
        self.mascot = Mascot(self)
        self.chat = Chat(self)
        self.mascot.show_all()

    def toggle_chat(self):
        if self.chat.get_visible():
            self.chat.hide()
        else:
            self.chat.show_all()
            self.chat.present()
            self.chat.entry.grab_focus()

    def explain_selection(self):
        """Whatever you highlighted anywhere on screen, explained. X11 PRIMARY selection."""
        clip = Gtk.Clipboard.get(Gdk.SELECTION_PRIMARY)
        text = clip.wait_for_text() or Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_text()
        if not text:
            self.toggle_chat()
            self.chat.say("sidekick", "Highlight some text first - a command, an error, a paragraph.")
            return
        self.chat.show_all()
        self.chat.present()
        self.chat.send("Explain this clearly and tell me what to do with it:\n\n" + text[:4000])

    def restart_model(self):
        subprocess.Popen(["systemctl", "--user", "restart", "sidekick-ai"])
        self.chat.show_all()
        self.chat.say("sidekick", "Restarting the local model. Give it a few seconds.")


if __name__ == "__main__":
    App()
    Gtk.main()
