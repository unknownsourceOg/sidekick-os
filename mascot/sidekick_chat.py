#!/usr/bin/env python3
"""Sidekick's native desktop hub, chat and guided creative controls."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import gi
gi.require_version('Gtk', '3.0')
gi.require_foreign('cairo')
from gi.repository import Gtk, Gdk, Gio, GLib
from sidekick_core import (Store, DOMAINS, TOOLS, INSTALL_GROUPS, diagnostics,
                           launch_tool, memory_gib, first_code_block, run_readonly)
from sidekick_model import ModelManager, CATALOG, health, recommended_model, stream_reply, DownloadCancelled
from sidekick_mascot import Mascot
from sidekick_drawing import draw_friend, IDLE, THINK, TALK, ALERT
from sidekick_music import make_sketch, KEYS, STYLES

CSS = b'''
window.sk { background-color: #080f16; color: #dcebe9; }
.sk label { color: #dcebe9; }
.sk label.title { font-size: 25px; font-weight: bold; color: #a1f5d5; }
.sk label.subtitle { font-size: 14px; color: #91aaa9; }
.sk label.brand { font-size: 20px; font-weight: bold; letter-spacing: 2px; color: #55e7b4; }
.sk label.small { color: #87a5ac; font-size: 12px; }
.sk button { background-image: none; background-color: #10232d; color: #daf9ed;
  border: 1px solid #24414c; border-radius: 9px; padding: 10px 14px; box-shadow: none; }
.sk button:hover { background-color: #163b43; border-color: #42bc9b; }
.sk button:disabled { color: #607b81; background-color: #111c23; }
.sk button.primary { background-color: #155a48; border-color: #35b78e; }
.sk button.nav { border: 0; background-color: #0d1923; padding: 11px; }
.sk entry, .sk spinbutton { background-color: #10202a; color: #e4f6f0; border: 1px solid #2b4b55; padding: 8px; }
.sk textview, .sk textview text { background-color: #0c1922; color: #dcebe9;
  font-family: "JetBrains Mono", monospace; font-size: 13px; }
.sk progressbar trough { background-color: #152c36; min-height: 8px; }
.sk progressbar progress { background-color: #4adea8; min-height: 8px; }
.sk separator { background-color: #19313b; }
'''
PAGES = ('Home', 'Chat', 'Computer', 'Code', 'Music', 'Animation', 'AI Setup', 'Activity')


def label(text, style=None):
    w=Gtk.Label(label=text);w.set_xalign(0);w.set_line_wrap(True)
    if style:w.get_style_context().add_class(style)
    return w


def button(text, callback, primary=False):
    w=Gtk.Button(label=text);w.connect('clicked',lambda *_:callback())
    if primary:w.get_style_context().add_class('primary')
    return w


class FriendView(Gtk.DrawingArea):
    def __init__(self,app):
        super().__init__();self.app=app;self.set_size_request(150,165)
        self.connect('draw',lambda w,cr:draw_friend(cr,w.get_allocated_width(),w.get_allocated_height(),time.monotonic(),app.mascot.mood))
        GLib.timeout_add(70,self.tick)
    def tick(self):self.queue_draw();return True


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.sidekick.Desktop', flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        for name in ('background','setup','smoke-test'):
            self.add_main_option(name,0,GLib.OptionFlags.NONE,GLib.OptionArg.NONE,name,None)
        self.add_main_option('screenshot',0,GLib.OptionFlags.NONE,GLib.OptionArg.STRING,'Screenshot path','PATH')
        self.store=Store(os.environ.get("SIDEKICK_TEST_HOME") if "--smoke-test" in sys.argv else None);self.model=ModelManager(self.store);self.window=None;self.smoke=False
        self.task_busy=False;self.chat_busy=False;self.chat_cancel=threading.Event();self.chat_response=None
        self.current_reply='';self.last_diagnostics='';self.exit_code=0;self.checking_health=False

    def do_command_line(self,command):
        options=command.get_options_dict().end()
        opts=options.unpack()
        self.smoke=bool(opts.get('smoke-test'))
        self.screenshot=opts.get('screenshot')
        self.activate()
        if opts.get('setup'):self.show_page('AI Setup')
        elif not opts.get('background') or not self.store.settings.get('welcomed'):self.show_page('Home')
        if self.smoke:GLib.timeout_add(900,self.smoke_test)
        return 0

    def do_activate(self):
        if self.window:return
        provider=Gtk.CssProvider();provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.mascot=Mascot(self);self.add_window(self.mascot);self.mascot.show_all()
        self.window=Gtk.ApplicationWindow(application=self,title='Sidekick • your desktop companion')
        self.window.get_style_context().add_class('sk')
        screen=self.window.get_screen()
        self.window.set_default_size(min(1040,screen.get_width()-60),min(740,screen.get_height()-60))
        self.window.connect('delete-event',self.hide_window)
        outer=Gtk.Box(spacing=0);self.window.add(outer)
        nav=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);nav.set_size_request(175,-1)
        for side in ('start','end','top','bottom'):getattr(nav,'set_margin_'+side)(15)
        nav.pack_start(label('SIDEKICK','brand'),False,False,12)
        nav.pack_start(label('Your desktop companion','small'),False,False,0)
        self.stack=Gtk.Stack();self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(160)
        for name in PAGES:
            b=button(name,lambda n=name:self.show_page(n));b.get_style_context().add_class('nav')
            nav.pack_start(b,False,False,0)
        self.status=label('Checking local AI…','small');nav.pack_end(self.status,False,False,8)
        nav.pack_end(label('Local tools • no subscription','small'),False,False,0)
        outer.pack_start(nav,False,False,0);outer.pack_start(Gtk.Separator(),False,False,0)
        outer.pack_start(self.stack,True,True,0)
        self.pages={}
        for name in PAGES:
            sw=Gtk.ScrolledWindow();sw.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
            body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=13)
            for side in ('start','end','top','bottom'):getattr(body,'set_margin_'+side)(24)
            sw.add(body);self.stack.add_named(sw,name);self.pages[name]=body
        self.make_home();self.make_chat();self.make_computer();self.make_code()
        self.make_music();self.make_animation();self.make_setup();self.make_activity()
        self.poll_health();GLib.timeout_add_seconds(7,self.poll_health)
        GLib.timeout_add(1100,self.mark_ready)

    def mark_ready(self):
        if not self.exit_code:
            (self.store.root/'ui-ready').write_text(str(os.getpid()))
        return False

    def hide_window(self,*_):self.window.hide();return True

    def show_page(self,name):
        if self.window is None:self.activate()
        self.stack.set_visible_child_name(name)
        if name=='Activity' and not self.task_busy:self.activity_text.get_buffer().set_text(self.store.activity())
        self.window.show_all();self.window.present()
        if name=='Chat':self.prompt.grab_focus()
        if name=='Home' and not self.store.settings.get('welcomed'):self.store.configure(welcomed=True)

    def heading(self,page,title,subtitle):
        page.pack_start(label(title,'title'),False,False,0)
        page.pack_start(label(subtitle,'subtitle'),False,False,0)

    def row(self,page,items):
        row=Gtk.Box(spacing=10,homogeneous=True)
        for text,fn in items:row.pack_start(button(text,fn),True,True,0)
        page.pack_start(row,False,False,0)

    def make_home(self):
        page=self.pages['Home'];hero=Gtk.Box(spacing=14)
        hero.pack_start(FriendView(self),False,False,0)
        text=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=9)
        text.pack_start(label('Hey. What are we making?','title'),False,False,15)
        text.pack_start(label('I’m your companion for the computer, code, music and animation. Choose a place to start.','subtitle'),False,False,0)
        hero.pack_start(text,True,True,0);page.pack_start(hero,False,False,0)
        self.row(page,[('Computer help',lambda:self.show_page('Computer')),('Write & fix code',lambda:self.show_page('Code'))])
        self.row(page,[('Make music',lambda:self.show_page('Music')),('Create animation',lambda:self.show_page('Animation'))])
        page.pack_start(button('Set up my free local AI',lambda:self.show_page('AI Setup'),True),False,False,7)
        page.pack_start(label('The tools work on their own. Chat becomes available after a model is downloaded. You review file changes and installations before they happen.','small'),False,False,0)
        page.pack_start(label('Tip: drag your floating companion anywhere. Click him to return here. Right-click for quick actions.','small'),False,False,0)

    def make_chat(self):
        page=self.pages['Chat'];self.heading(page,'Ask Sidekick','Explain a problem, paste code, or work on an idea together.')
        self.domain=Gtk.ComboBoxText()
        for name in DOMAINS:self.domain.append_text(name)
        self.domain.set_active(0);self.domain.connect('changed',lambda *_:self.load_chat())
        page.pack_start(self.domain,False,False,0)
        sw=Gtk.ScrolledWindow();sw.set_min_content_height(290)
        self.conversation=Gtk.TextView();self.conversation.set_editable(False)
        self.conversation.set_wrap_mode(Gtk.WrapMode.WORD_CHAR);self.conversation.set_left_margin(12);self.conversation.set_right_margin(12)
        sw.add(self.conversation);page.pack_start(sw,True,True,0)
        self.prompt=Gtk.Entry();self.prompt.set_placeholder_text('Tell me what you need, or paste an error…')
        self.prompt.connect('activate',lambda *_:self.send());page.pack_start(self.prompt,False,False,0)
        row=Gtk.Box(spacing=9)
        self.send_button=button('Ask',self.send,True);row.pack_start(self.send_button,True,True,0)
        row.pack_start(button('Stop',self.cancel_chat),False,False,0)
        row.pack_start(button('Save reply / code',self.save_reply),False,False,0)
        page.pack_start(row,False,False,0)
        page.pack_start(label('Saved chat stays on this computer. Suggestions are not automatically executed.','small'),False,False,0)
        self.load_chat()

    def load_chat(self):
        if not hasattr(self,'conversation'):return
        self.current_reply='';buf=self.conversation.get_buffer();buf.set_text('')
        for turn in self.store.history(self.domain.get_active_text()):
            self.append_chat(('You' if turn['role']=='user' else 'Sidekick')+'\n'+turn['content']+'\n\n')

    def append_chat(self,text):
        buf=self.conversation.get_buffer();buf.insert(buf.get_end_iter(),text)
        mark=buf.create_mark(None,buf.get_end_iter(),False);self.conversation.scroll_mark_onscreen(mark);buf.delete_mark(mark)
        return False

    def ask_about(self,domain,prompt):
        if self.chat_busy:
            self.notice('One answer at a time','Stop the current answer or let it finish first.');return
        self.domain.set_active(list(DOMAINS).index(domain));self.show_page('Chat');self.prompt.set_text(prompt)

    def send(self):
        prompt=self.prompt.get_text().strip()
        if not prompt or self.chat_busy:return
        domain=self.domain.get_active_text();history=self.store.history(domain)
        self.prompt.set_text('');self.append_chat('You\n'+prompt+'\n\nSidekick\n')
        self.current_reply='';self.chat_busy=True;self.chat_cancel.clear();self.chat_response=None
        self.domain.set_sensitive(False);self.send_button.set_sensitive(False);self.mascot.set_mood(THINK)
        def work():
            try:
                answer=stream_reply(domain,history,prompt,lambda s:GLib.idle_add(self.chat_chunk,s),self.chat_cancel,
                                    on_response=lambda r:setattr(self,'chat_response',r))
                if not self.chat_cancel.is_set() and answer:
                    self.store.save_history(domain,history+[{'role':'user','content':prompt},{'role':'assistant','content':answer}])
                GLib.idle_add(self.finish_chat,answer,None)
            except Exception as exc:
                GLib.idle_add(self.finish_chat,'',str(exc))
        threading.Thread(target=work,daemon=True).start()

    def chat_chunk(self,chunk):
        if not self.chat_cancel.is_set():self.current_reply+=chunk;self.append_chat(chunk);self.mascot.set_mood(TALK)
        return False

    def finish_chat(self,answer,error):
        if self.chat_cancel.is_set():self.append_chat('\n[Stopped]\n')
        elif error:
            self.append_chat('\nThe local AI could not answer. Open AI Setup to download/start it, or check AI logs in Activity.\n'+error+'\n')
            self.store.log('Chat error',error);self.mascot.set_mood(ALERT)
        else:self.current_reply=answer
        self.append_chat('\n\n');self.chat_busy=False;self.chat_response=None
        self.domain.set_sensitive(True);self.send_button.set_sensitive(True)
        GLib.timeout_add(2200,lambda:self.mascot.set_mood(IDLE) or False)
        return False

    def cancel_chat(self):
        self.chat_cancel.set()
        response=self.chat_response
        if response:threading.Thread(target=response.close,daemon=True).start()

    def save_reply(self):
        if self.chat_busy or not self.current_reply:
            self.notice('No completed reply','Finish an answer before saving it.');return
        dialog=Gtk.FileChooserDialog(title='Save this reply or its first code block',parent=self.window,
            action=Gtk.FileChooserAction.SAVE)
        dialog.add_buttons('Cancel',Gtk.ResponseType.CANCEL,'Save',Gtk.ResponseType.OK)
        dialog.set_do_overwrite_confirmation(True);dialog.set_current_name('sidekick-draft.txt')
        dialog.set_current_folder(str(self.store.home))
        if dialog.run()==Gtk.ResponseType.OK:
            try:
                backup=self.store.save_reply(dialog.get_filename(),first_code_block(self.current_reply))
                self.notice('Saved',('Previous version backed up to:\n'+str(backup)) if backup else 'Your draft is saved. Review code before running it.')
            except Exception as exc:self.notice('Could not save',str(exc))
        dialog.destroy()

    def make_computer(self):
        p=self.pages['Computer'];self.heading(p,'Let’s look after your computer','Open familiar settings or run a read-only system check.')
        for keys in [('files','settings'),('network','sound'),('power',)]:
            self.row(p,[(TOOLS[k][0],lambda key=k:self.open_tool(key)) for k in keys])
        self.row(p,[('Check my system',self.system_check),('Explain the last check',self.explain_check)])
        p.pack_start(label('The check reads system information. It does not reformat drives, remove software or run AI-written commands.','small'),False,False,0)

    def make_code(self):
        p=self.pages['Code'];self.heading(p,'Build something that works','Draft code, understand errors, and save reviewed changes with a backup.')
        self.row(p,[('Open code editor',lambda:self.open_tool('editor')),('Install code editor',lambda:self.install_tools('code'))])
        for title,prompt in [('Fix an error','Help me diagnose this error. I will paste the code and error next.'),
                             ('Build a project','Help me build a small project. First help me define the inputs, outputs and language.'),
                             ('Review a change','Review the code I paste for bugs and suggest a meaningful way to test it.')]:
            p.pack_start(button(title,lambda q=prompt:self.ask_about('Code',q)),False,False,0)
        p.pack_start(label('Use Save reply / code in Chat to create a file. Existing files receive a backup before replacement.','small'),False,False,0)

    def make_music(self):
        p=self.pages['Music'];self.heading(p,'Your music workbench','Write, arrange, record and build editable musical ideas.')
        self.row(p,[('Record / edit audio',lambda:self.open_tool('audacity')),('Open LMMS',lambda:self.open_tool('lmms'))])
        p.pack_start(button('Install free music tools',lambda:self.install_tools('music')),False,False,0)
        self.row(p,[('Write / arrange a song',lambda:self.ask_about('Music','Help me write an original song. Ask about mood, style, vocal range and instruments.')),
                    ('Mixing help',lambda:self.ask_about('Music','Help me plan a mix. Ask about the tracks and the sound I want.'))])
        p.pack_start(label('Make an editable MIDI starter','subtitle'),False,False,4)
        row=Gtk.Box(spacing=10);self.music_key=Gtk.ComboBoxText();self.music_style=Gtk.ComboBoxText()
        for k in KEYS:self.music_key.append_text(k)
        for s in STYLES:self.music_style.append_text(s)
        self.music_key.set_active(0);self.music_style.set_active(0)
        self.bpm=Gtk.SpinButton.new_with_range(40,220,1);self.bpm.set_value(110)
        for title,w in [('Key',self.music_key),('Style',self.music_style),('BPM',self.bpm)]:
            col=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5);col.pack_start(label(title,'small'),False,False,0)
            col.pack_start(w,False,False,0);row.pack_start(col,True,True,0)
        p.pack_start(row,False,False,0)
        p.pack_start(button('Create 8-bar MIDI sketch',self.music_sketch,True),False,False,0)
        p.pack_start(label('Creates separate chords, bass and drums for importing into LMMS or another DAW. You choose the instruments. This is MIDI, not a finished audio recording.','small'),False,False,0)

    def music_sketch(self):
        try:
            folder=self.store.new_project('Music')
            path=make_sketch(folder,self.music_key.get_active_text(),self.bpm.get_value_as_int(),self.music_style.get_active_text())
            self.store.log('MIDI sketch',path);self.notice('Your sketch is ready',f'Import starter.mid into LMMS.\n\n{folder}')
            launch_tool('files',[folder])
        except Exception as exc:self.notice('Could not create the sketch',str(exc))

    def make_animation(self):
        p=self.pages['Animation'];self.heading(p,'Bring an idea to life','Plan motion, write animation code, and work in free creative tools.')
        self.row(p,[('Open Blender',lambda:self.open_tool('blender')),('Open video editor',lambda:self.open_tool('kdenlive'))])
        p.pack_start(button('Install free animation tools',lambda:self.install_tools('animation')),False,False,0)
        self.row(p,[('Plan a scene',lambda:self.ask_about('Animation','Help me storyboard an animation. Ask about the character, style, action and duration.')),
                    ('Animation coding',lambda:self.ask_about('Animation','Help me write animation code. Ask whether I am using Blender, a game engine or a web project.'))])
        p.pack_start(button('Create a 3D animation starter',self.animation_starter,True),False,False,6)
        p.pack_start(label('Creates a new Blender project with a lit, rotating object, camera and a four-second timeline. Open it to play or render the animation.','small'),False,False,0)

    def animation_starter(self):
        if self.task_busy:
            self.notice('A task is running','Let the current task finish first.');return
        binary=shutil.which('blender')
        if not binary:self.notice('Install Blender first','Choose Install free animation tools on this page.');return
        folder=self.store.new_project('Animation')
        template=Path(__file__).parent/'templates/animation_starter.py'
        def work():
            self.process([binary,'--background','--factory-startup','--python-exit-code','1','--python',str(template),'--','--output',str(folder)])
            target=folder/'sidekick-starter.blend'
            if not target.is_file():raise RuntimeError('Blender did not create the project.')
            launch_tool('blender',[target]);self.store.log('Animation starter',target)
        self.task('Create animation starter',work)

    def make_setup(self):
        p=self.pages['AI Setup'];self.heading(p,'Meet your local AI','Choose a free model that fits your computer. Chat runs locally after the download.')
        ram=memory_gib();p.pack_start(label(f'Detected memory: {ram:.1f} GiB','subtitle'),False,False,0)
        self.models=Gtk.ComboBoxText();recommend=recommended_model(ram)
        for key,m in CATALOG.items():
            note=' • suggested for this computer' if key==recommend else ''
            self.models.append(key,f"{m['name']} • {m['bytes']/1024**3:.1f} GiB download • {m['minimum_ram_gib']} GB RAM{note}")
        self.models.set_active_id(recommend or next(iter(CATALOG)))
        p.pack_start(self.models,False,False,0)
        p.pack_start(label('Larger models can handle more complex tasks but use more memory and may answer more slowly. All options use openly licensed Qwen models.','small'),False,False,0)
        self.folder_label=label('Model folder: '+str(self.model.storage),'small');p.pack_start(self.folder_label,False,False,0)
        self.row(p,[('Choose storage folder',self.choose_storage),('Download & set up AI',self.install_model)])
        self.row(p,[('Start AI',lambda:self.model_service('start')),('Restart AI',lambda:self.model_service('restart')),('Stop AI',lambda:self.model_service('stop'))])
        p.pack_start(button('Pause download',lambda:self.model.stop.set()),False,False,0)
        self.setup_status=label('Choose a model when you are ready.','small');p.pack_start(self.setup_status,False,False,0)
        self.download_progress=Gtk.ProgressBar();p.pack_start(self.download_progress,False,False,0)
        p.pack_start(label('Using a live USB? Downloads and chats survive reboot only when saved on persistent storage. Before downloading several gigabytes, choose a folder on a drive where you keep your files.','small'),False,False,0)
        p.pack_start(label('The model helps with text, code, music planning and animation scripts. Audio recording and 3D rendering use the creative tools.','small'),False,False,0)

    def choose_storage(self):
        if self.task_busy:self.notice('A task is running','Finish or pause the current download first.');return
        d=Gtk.FileChooserDialog(title='Choose a folder to keep the AI model',parent=self.window,action=Gtk.FileChooserAction.SELECT_FOLDER)
        d.add_buttons('Cancel',Gtk.ResponseType.CANCEL,'Use folder',Gtk.ResponseType.OK)
        if d.run()==Gtk.ResponseType.OK:
            self.store.configure(model_folder=d.get_filename());self.folder_label.set_text('Model folder: '+str(self.model.storage))
        d.destroy()

    def install_model(self):
        key=self.models.get_active_id();m=CATALOG[key]
        if not self.confirm('Set up '+m['name']+'?',f"Download {m['bytes']/1024**3:.1f} GiB to:\n{self.model.storage}\n\nThis uses internet data. Choose persistent storage to keep it after reboot."):return
        self.task('Set up local AI',lambda:self.model.install(key,self.model_progress))

    def model_progress(self,text,fraction):
        GLib.idle_add(self.setup_status.set_text,text)
        GLib.idle_add(self.download_progress.set_fraction,max(0,min(1,fraction)))

    def model_service(self,operation):self.task('AI '+operation,lambda:self.model.service(operation))

    def make_activity(self):
        p=self.pages['Activity'];self.heading(p,'What happened','See task progress, errors and previous actions.')
        self.task_label=label('Ready.','subtitle');p.pack_start(self.task_label,False,False,0)
        self.task_progress=Gtk.ProgressBar();p.pack_start(self.task_progress,False,False,0)
        self.activity_text=Gtk.TextView();self.activity_text.set_editable(False);self.activity_text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        sw=Gtk.ScrolledWindow();sw.set_min_content_height(310);sw.add(self.activity_text);p.pack_start(sw,True,True,0)
        self.row(p,[('Refresh activity',lambda:self.show_page('Activity')),('AI logs',self.ai_logs)])

    def task(self,name,work):
        if self.task_busy:self.notice('A task is running','Let the current task finish before starting another.');return
        self.task_busy=True;self.show_page('Activity');self.task_label.set_text(name+'…');self.mascot.set_mood(THINK)
        self.activity_text.get_buffer().set_text('')
        GLib.timeout_add(150,self.pulse_task)
        def run():
            try:work();GLib.idle_add(self.finish_task,name,None)
            except Exception as exc:GLib.idle_add(self.finish_task,name,str(exc))
        threading.Thread(target=run,daemon=True).start()

    def pulse_task(self):
        if self.task_busy:self.task_progress.pulse()
        return self.task_busy

    def task_line(self,text):
        b=self.activity_text.get_buffer();b.insert(b.get_end_iter(),text)
        if b.get_char_count()>160000:b.delete(b.get_start_iter(),b.get_iter_at_offset(80000))
        return False

    def process(self,command):
        with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1) as p:
            for line in p.stdout:GLib.idle_add(self.task_line,line)
            code=p.wait()
        if code in (126,127) and command[0]=='pkexec':raise RuntimeError('Installation was cancelled or desktop authorization was unavailable.')
        if code:raise RuntimeError(f'The operation stopped with status {code}. The output above has the details.')

    def finish_task(self,name,error):
        self.task_busy=False;message='Completed.' if error is None else error
        self.task_label.set_text(name+' — '+message);self.task_progress.set_fraction(1 if error is None else 0)
        self.store.log(name,message);self.task_line('\n'+message+'\n')
        self.mascot.set_mood(IDLE if error is None else ALERT);self.poll_health()
        return False

    def install_tools(self,key):
        group=INSTALL_GROUPS[key]
        explanation=group[1]+' will be downloaded from Debian and installed. The desktop may ask for your login password.'
        try:
            if 'boot=live' in Path('/proc/cmdline').read_text():
                explanation+=' Fresh live sessions use the password “live” unless you changed it.'
        except OSError:pass
        if not self.confirm('Install '+group[0].lower()+'?',explanation):return
        self.task('Install '+group[0].lower(),lambda:self.process(['pkexec','/usr/local/libexec/sidekick-admin',key]))

    def open_tool(self,key):
        try:launch_tool(key);self.store.log('Open '+TOOLS[key][0],'Launch requested.')
        except Exception as exc:self.notice('Could not open the tool',str(exc))

    def system_check(self):
        def work():
            self.last_diagnostics=diagnostics(self.store.home);GLib.idle_add(self.task_line,self.last_diagnostics+'\n')
        self.task('Read-only system check',work)

    def explain_check(self):
        if not self.last_diagnostics:self.notice('Run a check first','Choose Check my system, then ask me to explain it.');return
        self.ask_about('Computer','Explain these diagnostic results and suggest the next safe steps.\n\n'+self.last_diagnostics)

    def ai_logs(self):
        self.task('Read AI logs',lambda:GLib.idle_add(self.task_line,run_readonly(['journalctl','--user','-u','sidekick-ai','--no-pager','-n','80'])))

    def poll_health(self):
        if self.checking_health or not hasattr(self,'status'):return True
        self.checking_health=True
        def work():
            ready=health()
            GLib.idle_add(self.update_health,ready)
        threading.Thread(target=work,daemon=True).start();return True

    def update_health(self,ready):
        self.status.set_text('● AI ready • on this computer' if ready else '○ AI offline • open AI Setup')
        self.checking_health=False;return False

    def explain_selection(self):
        text=Gtk.Clipboard.get(Gdk.SELECTION_PRIMARY).wait_for_text() or Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_text()
        if text:self.ask_about('Computer','Explain this and help me choose what to do next:\n\n'+text[:8000])
        else:self.notice('Select some text first','Highlight the error or code, then choose Explain highlighted text.')

    def notice(self,title,text):
        d=Gtk.MessageDialog(transient_for=self.window,modal=True,message_type=Gtk.MessageType.INFO,buttons=Gtk.ButtonsType.OK,text=title)
        d.format_secondary_text(text);d.run();d.destroy()

    def confirm(self,title,text):
        d=Gtk.MessageDialog(transient_for=self.window,modal=True,message_type=Gtk.MessageType.QUESTION,buttons=Gtk.ButtonsType.CANCEL,text=title)
        d.format_secondary_text(text);d.add_button('Continue',Gtk.ResponseType.OK)
        result=d.run()==Gtk.ResponseType.OK;d.destroy();return result

    def smoke_test(self):
        try:
            assert len(self.pages)==8 and self.mascot.get_visible()
            assert self.models.get_active_id() in CATALOG
            for name in PAGES:
                self.stack.set_visible_child_name(name)
                assert self.stack.get_visible_child_name()==name
            self.show_page('Home')
            GLib.timeout_add(400,self.finish_smoke)
        except Exception:
            self.exit_code=1;raise
        return False

    def finish_smoke(self):
        if self.screenshot:
            path=Path(self.screenshot);path.parent.mkdir(parents=True,exist_ok=True)
            window=self.window.get_window();a=self.window.get_allocation()
            pix=Gdk.pixbuf_get_from_window(window,0,0,a.width,a.height)
            if pix is None:raise RuntimeError('The GUI did not render.')
            pix.savev(str(path),'png',[],[])
        if not self.exit_code:print('SIDEKICK_GUI_OK',flush=True)
        self.quit();return False


def main():
    app=App()
    original=sys.excepthook
    def handle_error(kind,value,tb):
        original(kind,value,tb)
        app.exit_code=1
        if app.smoke:app.quit()
    sys.excepthook=handle_error
    return max(app.run(sys.argv),app.exit_code)

if __name__=='__main__':raise SystemExit(main())
