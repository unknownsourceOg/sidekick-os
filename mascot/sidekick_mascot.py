#!/usr/bin/env python3
"""The persistent native desktop companion."""
import time
import gi
gi.require_version('Gtk', '3.0')
gi.require_foreign('cairo')
from gi.repository import Gtk, Gdk, GLib
from sidekick_drawing import draw_friend, IDLE, THINK, TALK, ALERT


class Mascot(Gtk.Window):
    def __init__(self, app):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.app=app; self.mood=IDLE; self.started=time.monotonic(); self.drag=None; self.moved=False
        self.set_decorated(False); self.set_keep_above(True); self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True); self.set_accept_focus(False); self.set_app_paintable(True)
        self.set_default_size(144,162); self.set_resizable(False)
        self.set_visual(self.get_screen().get_rgba_visual() or self.get_visual())
        self.set_title('Sidekick companion'); self.connect('draw',self.draw)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        self.connect('button-press-event',self.press); self.connect('motion-notify-event',self.motion)
        self.connect('button-release-event',self.release)
        s=self.get_screen(); self.move(max(0,s.get_width()-170),max(0,s.get_height()-210))
        GLib.timeout_add(45,self.tick)

    def tick(self):
        self.queue_draw(); return True

    def draw(self,widget,cr):
        a=self.get_allocation(); draw_friend(cr,a.width,a.height,time.monotonic()-self.started,self.mood)
        return False

    def press(self,w,event):
        if event.button==3:
            menu=Gtk.Menu()
            for label,fn in [('Open Sidekick',lambda:self.app.show_page('Home')),
                             ('Explain highlighted text',self.app.explain_selection),
                             ('Computer tools',lambda:self.app.show_page('Computer')),
                             ('Music studio',lambda:self.app.show_page('Music')),
                             ('Animation studio',lambda:self.app.show_page('Animation')),
                             ('AI setup',lambda:self.app.show_page('AI Setup')),
                             ('Quit Sidekick',self.app.quit)]:
                item=Gtk.MenuItem(label=label);item.connect('activate',lambda _,f=fn:f());menu.append(item)
            menu.show_all();menu.popup_at_pointer(event);return True
        if event.button==1:
            self.drag=(event.x_root,event.y_root,*self.get_position());self.moved=False
        return True

    def motion(self,w,event):
        if self.drag:
            dx=event.x_root-self.drag[0];dy=event.y_root-self.drag[1]
            if abs(dx)>5 or abs(dy)>5:
                self.moved=True
                screen=self.get_screen()
                self.move(max(0,min(screen.get_width()-144,int(self.drag[2]+dx))),
                          max(0,min(screen.get_height()-162,int(self.drag[3]+dy))))
        return True

    def release(self,w,event):
        if self.drag and not self.moved and event.button==1:self.app.show_page('Home')
        self.drag=None;return True

    def set_mood(self,mood):self.mood=mood
