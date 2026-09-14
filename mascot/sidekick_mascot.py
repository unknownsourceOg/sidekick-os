#!/usr/bin/env python3
"""
Sidekick — the animated companion that sits on top of every window.

Pure GTK3 + Cairo: no images, no web engine, ~30 MB RAM. It draws a sci-fi
core that idles, thinks and talks, and it is click-through everywhere except
on the mascot itself, so it never gets in your way.

Left click  : open / close the chat
Drag        : move it
Right click : menu (explain what I highlighted, restart the model, quit)
"""
import gi, json, math, os, threading, time, urllib.request, urllib.error, subprocess
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf, cairo  # noqa
import cairo as C

API = os.environ.get("SIDEKICK_API", "http://127.0.0.1:8080/v1/chat/completions")
MODEL = os.environ.get("SIDEKICK_MODEL", "local")
PERSONA = (
    "You are Sidekick, the assistant built into this operating system. You belong to one person. "
    "Answer short and concrete. For code: give the exact command or the minimal working snippet first, "
    "then one line on why. Teach by doing. Say plainly when you do not know. "
    "Flag security and privacy risks when you notice them."
)
IDLE, THINK, TALK, ALERT = 0, 1, 2, 3
SIZE = 92
GREEN, CYAN, AMBER, RED = (0.29, 0.87, 0.61), (0.35, 0.83, 1.0), (1.0, 0.71, 0.33), (1.0, 0.42, 0.42)


class Mascot(Gtk.Window):
    def __init__(self, app):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.app = app
        self.mood = IDLE
        self.t0 = time.time()
        self.set_app_paintable(True)
        self.set_keep_above(True)
        self.set_accept_focus(False)
        self.set_default_size(SIZE, SIZE)
        self.set_visual(self.get_screen().get_rgba_visual() or self.get_visual())
        self.connect("draw", self.on_draw)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                        | Gdk.EventMask.POINTER_MOTION_MASK)
        self.connect("button-press-event", self.on_press)
        self.connect("button-release-event", self.on_release)
        self.connect("motion-notify-event", self.on_motion)
        s = self.get_screen()
        self.move(s.get_width() - SIZE - 26, int(s.get_height() * 0.62))
        self.drag = None
        self.moved = False
        GLib.timeout_add(45, self.tick)

    def tick(self):
        self.queue_draw()
        return True

    def on_draw(self, w, cr):
        t = time.time() - self.t0
        cr.set_operator(C.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(C.OPERATOR_OVER)
        col = {IDLE: GREEN, THINK: CYAN, TALK: GREEN, ALERT: AMBER}[self.mood]
        cx = cy = SIZE / 2
        beat = 1 + 0.05 * math.sin(t * (4.5 if self.mood == THINK else 2.0))
        r = SIZE * 0.30 * beat

        # outer glow
        g = C.RadialGradient(cx, cy, r * 0.4, cx, cy, r * 1.85)
        g.add_color_stop_rgba(0, *col, 0.42)
        g.add_color_stop_rgba(1, *col, 0.0)
        cr.set_source(g)
        cr.arc(cx, cy, r * 1.85, 0, 7)
        cr.fill()

        # rotating containment rings
        for i, (rr, sp, a) in enumerate(((1.55, 0.7, 0.55), (1.32, -1.1, 0.4))):
            cr.save()
            cr.translate(cx, cy)
            cr.rotate(t * sp + i)
            cr.set_source_rgba(*col, a)
            cr.set_line_width(1.6)
            cr.scale(1.0, 0.34)
            cr.arc(0, 0, r * rr, 0, 7)
            cr.stroke()
            cr.restore()

        # core
        core = C.RadialGradient(cx - r * 0.3, cy - r * 0.35, r * 0.1, cx, cy, r)
        core.add_color_stop_rgba(0, 1, 1, 1, 0.95)
        core.add_color_stop_rgba(0.45, *col, 0.95)
        core.add_color_stop_rgba(1, col[0] * 0.35, col[1] * 0.35, col[2] * 0.35, 0.95)
        cr.set_source(core)
        cr.arc(cx, cy, r, 0, 7)
        cr.fill()

        # scanlines across the core
        cr.save()
        cr.arc(cx, cy, r, 0, 7)
        cr.clip()
        cr.set_source_rgba(0, 0, 0, 0.20)
        off = (t * 22) % 6
        y = cy - r
        while y < cy + r:
            cr.rectangle(cx - r, y + off, 2 * r, 1.4)
            y += 6
        cr.restore()
        cr.fill()

        # eye / mouth signature
        cr.set_line_width(2.4)
        cr.set_source_rgba(0.04, 0.06, 0.08, 0.92)
        if self.mood == THINK:
            for i in range(3):
                a = math.sin(t * 5 - i * 0.9)
                cr.arc(cx + (i - 1) * r * 0.42, cy - a * r * 0.12, r * 0.09, 0, 7)
                cr.fill()
        elif self.mood == TALK:
            n = 7
            cr.move_to(cx - r * 0.5, cy)
            for i in range(1, n + 1):
                x = cx - r * 0.5 + (r * 1.0) * i / n
                cr.line_to(x, cy + (-1 if i % 2 else 1) * r * 0.30
                           * abs(math.sin(t * 12 + i)))
            cr.stroke()
        elif self.mood == ALERT:
            cr.move_to(cx, cy - r * 0.42)
            cr.line_to(cx, cy + r * 0.12)
            cr.stroke()
            cr.arc(cx, cy + r * 0.34, 1.9, 0, 7)
            cr.fill()
        else:
            blink = abs(math.sin(t * 0.7)) ** 12
            h = r * 0.30 * (1 - blink)
            cr.move_to(cx - r * 0.34, cy)
            cr.curve_to(cx - r * 0.1, cy - h, cx + r * 0.1, cy - h, cx + r * 0.34, cy)
            cr.stroke()

        # input region = the mascot only, so clicks pass through everywhere else
        reg = C.Region(C.RectangleInt(int(cx - r * 1.15), int(cy - r * 1.15),
                                      int(r * 2.3), int(r * 2.3)))
        self.input_shape_combine_region(reg)
        return False

    # ---- interaction ----
    def on_press(self, w, e):
        if e.button == 3:
            self.menu(e)
            return True
        self.drag = (e.x_root, e.y_root, *self.get_position())
        self.moved = False
        return True

    def on_motion(self, w, e):
        if not self.drag:
            return False
        dx, dy = e.x_root - self.drag[0], e.y_root - self.drag[1]
        if abs(dx) > 5 or abs(dy) > 5:
            self.moved = True
            self.move(int(self.drag[2] + dx), int(self.drag[3] + dy))
        return True

    def on_release(self, w, e):
        if self.drag and not self.moved and e.button == 1:
            self.app.toggle_chat()
        self.drag = None
        return True

    def menu(self, e):
        m = Gtk.Menu()
        for label, fn in (("Explain what I highlighted", self.app.explain_selection),
                          ("Open chat", self.app.toggle_chat),
                          ("Restart the model", self.app.restart_model),
                          ("Quit Sidekick", lambda *_: Gtk.main_quit())):
            it = Gtk.MenuItem(label=label)
            it.connect("activate", lambda _w, f=fn: f())
            m.append(it)
        m.show_all()
        m.popup_at_pointer(e)

    def set_mood(self, m):
        self.mood = m
