import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
import hashlib
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'mascot'))
import sidekick_core as core
import sidekick_model as model
import sidekick_music as music
import mido


class FileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.home=Path(self.temp.name)/'home';self.home.mkdir()
        self.store=core.Store(self.home)
    def tearDown(self):self.temp.cleanup()
    def test_replace_preserves_original(self):
        path=self.home/'project/main.py';path.parent.mkdir();path.write_text('original\n');path.chmod(0o640)
        backup=self.store.save_reply(path,'reviewed\n')
        self.assertEqual(backup.read_text(),'original\n');self.assertEqual(path.read_text(),'reviewed\n')
        self.assertEqual(path.stat().st_mode&0o777,0o640)
    def test_escape_and_symlink_do_not_touch_external_file(self):
        external=Path(self.temp.name)/'untouched';external.write_text('keep')
        link=self.home/'link';link.symlink_to(external)
        for path in (external,link):
            with self.assertRaises(ValueError):self.store.save_reply(path,'replace')
        self.assertEqual(external.read_text(),'keep')
    def test_histories_are_separate_and_truncated(self):
        turns=[{'role':'user','content':str(n)} for n in range(35)]
        self.store.save_history('Music',turns)
        self.assertEqual(len(self.store.history('Music')),20);self.assertEqual(self.store.history('Code'),[])
        with self.assertRaises(ValueError):self.store.history('../../outside')
    def test_corrupt_history_is_recoverable(self):
        (self.store.root/'chat-code.json').write_text('broken')
        self.assertEqual(self.store.history('Code'),[])
    def test_unknown_tools_never_start_a_process(self):
        with patch.object(core.subprocess,'Popen') as call:
            with self.assertRaises(ValueError):core.launch_tool('rm -rf /')
            call.assert_not_called()


class MusicTests(unittest.TestCase):
    def test_midi_can_be_read_and_all_notes_finish(self):
        with tempfile.TemporaryDirectory() as d:
            for style in music.STYLES:
                folder=Path(d)/style
                path=music.make_sketch(folder,key='G',bpm=123,style=style)
                midi=mido.MidiFile(path)
                self.assertEqual(midi.type,1);self.assertEqual(len(midi.tracks),4)
                self.assertEqual(next(x.tempo for x in midi.tracks[0] if x.type=='set_tempo'),round(60000000/123))
                for track in midi.tracks:
                    active={};ticks=0
                    for message in track:
                        self.assertGreaterEqual(message.time,0);ticks+=message.time
                        if message.type in ('note_on','note_off'):
                            key=(message.channel,message.note)
                            active[key]=active.get(key,0)+(1 if message.type=='note_on' and message.velocity else -1)
                            self.assertGreaterEqual(active[key],0)
                    self.assertTrue(all(n==0 for n in active.values()))
                    self.assertEqual(ticks,8*4*music.TPQ)
                with self.assertRaises(FileExistsError):music.make_sketch(folder)
    def test_invalid_tempo_creates_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):music.make_sketch(Path(d)/'no',bpm=0)
            self.assertFalse((Path(d)/'no').exists())


class Response(io.BytesIO):
    def __init__(self,data,status=200,headers=None):
        super().__init__(data);self.status=status;self.headers=headers or {}


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=core.Store(self.temp.name)
        self.manager=model.ModelManager(self.store)
        self.engine=Path(self.temp.name)/'llama-server';self.engine.write_text('test');self.engine.chmod(0o755)
        self.manager.engine=self.engine
        self.payload=b'GGUF'+bytes(range(255))*10
        self.record={'id':'test','name':'Test','repo':'Qwen/Test-GGUF','revision':'a'*40,
                     'filename':'test.gguf','bytes':len(self.payload),'sha256':hashlib.sha256(self.payload).hexdigest(),'minimum_ram_gib':4}
        self.catalog=patch.dict(model.CATALOG,{'test':self.record},clear=True);self.catalog.start()
        self.ram=patch.object(model,'memory_gib',return_value=8);self.ram.start()
    def tearDown(self):self.ram.stop();self.catalog.stop();self.temp.cleanup()
    def test_verified_download_activates_only_after_verification(self):
        with patch.object(self.manager,'activate') as activate:
            self.manager.install('test',lambda *_:None,opener=lambda request,**kw:Response(self.payload))
            activate.assert_called_once()
        self.assertEqual((self.manager.storage/'test.gguf').read_bytes(),self.payload)
    def test_bad_checksum_never_activates(self):
        with patch.object(self.manager,'activate') as activate:
            with self.assertRaisesRegex(RuntimeError,'checksum'):
                self.manager.install('test',lambda *_:None,opener=lambda request,**kw:Response(b'X'*len(self.payload)))
            activate.assert_not_called()
        self.assertFalse((self.manager.storage/'test.gguf').exists())
    def test_interrupted_download_resumes_from_exact_range(self):
        self.manager.storage.mkdir(parents=True);part=self.manager.storage/'test.gguf.part';part.write_bytes(self.payload[:100])
        def opener(request,**kw):
            self.assertEqual(request.headers['Range'],'bytes=100-')
            self.assertIn('/resolve/'+'a'*40+'/',request.full_url)
            return Response(self.payload[100:],206,{'Content-Range':f'bytes 100-{len(self.payload)-1}/{len(self.payload)}'})
        with patch.object(self.manager,'activate'):
            self.manager.install('test',lambda *_:None,opener=opener)
        self.assertFalse(part.exists())
    def test_cancel_does_not_activate_partial_model(self):
        def opener(*a,**kw):self.manager.stop.set();return Response(self.payload)
        with patch.object(self.manager,'activate') as activate:
            with self.assertRaises(model.DownloadCancelled):self.manager.install('test',lambda *_:None,opener=opener)
            activate.assert_not_called()
    def test_unit_paths_escape_percent_and_reject_newlines(self):
        self.assertEqual(model.unit_quote('/home/a/100% model'), '"/home/a/100%% model"')
        with self.assertRaises(ValueError):model.unit_quote('/home/a\nExecStart=bad')
    def test_model_text_cannot_execute_commands(self):
        message='rm -rf / is text, not an action.'
        stream=b'data: '+json.dumps({'choices':[{'delta':{'content':message}}]}).encode()+b'\n\ndata: [DONE]\n'
        chunks=[]
        def opener(request,**kw):
            self.assertTrue(request.full_url.startswith('http://127.0.0.1:8080/'))
            body=json.loads(request.data);self.assertFalse(body['chat_template_kwargs']['enable_thinking'])
            return Response(stream)
        with patch.object(model.subprocess,'run') as run:
            answer=model.stream_reply('Music',[],'Help',chunks.append,threading.Event(),opener=opener)
            run.assert_not_called()
        self.assertEqual(answer,message);self.assertEqual(''.join(chunks),message)


class AdminTests(unittest.TestCase):
    def test_bad_action_is_rejected_before_any_command(self):
        path=Path(__file__).resolve().parents[1]/'system/sidekick-admin'
        loader=importlib.machinery.SourceFileLoader('admin_helper',str(path))
        spec=importlib.util.spec_from_loader(loader.name,loader);admin=importlib.util.module_from_spec(spec);loader.exec_module(admin)
        with patch.object(admin.subprocess,'run') as run:
            for args in ([],['music','--extra'],['music;shutdown'],['--help']):
                self.assertEqual(admin.main(args),2)
            run.assert_not_called()
    def test_valid_group_uses_fixed_package_arguments(self):
        path=Path(__file__).resolve().parents[1]/'system/sidekick-admin'
        loader=importlib.machinery.SourceFileLoader('admin_fixed',str(path))
        spec=importlib.util.spec_from_loader(loader.name,loader);admin=importlib.util.module_from_spec(spec);loader.exec_module(admin)
        with patch.object(admin.os,'geteuid',return_value=0),patch.object(admin.subprocess,'run') as run:
            run.return_value.returncode=0
            self.assertEqual(admin.main(['music']),0)
            self.assertEqual(run.call_args_list[1].args[0],['/usr/bin/apt-get','install','-y','--no-install-recommends','audacity','lmms'])
            self.assertNotIn('shell',run.call_args.kwargs)

if __name__=='__main__':unittest.main()
