"""Verified model downloads and a user service for the bundled local engine."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request

from sidekick_core import atomic_write, memory_gib, PERSONA, DOMAINS

API = 'http://127.0.0.1:8080'
CATALOG = json.loads(Path(__file__).with_name('models.json').read_text())


def recommended_model(ram=None):
    ram = memory_gib() if ram is None else ram
    # MemTotal is slightly below the marketed RAM size.
    eligible = [m for m in CATALOG.values() if ram >= m['minimum_ram_gib'] - 0.6]
    return max(eligible, key=lambda m: m['minimum_ram_gib'])['id'] if eligible else None


def health():
    try:
        with urllib.request.urlopen(API + '/health', timeout=2) as response:
            data = json.load(response)
        return data.get('status') == 'ok'
    except (OSError, ValueError):
        return False


def unit_quote(value):
    if any(c in str(value) for c in ("\n", "\r", "\x00")):
        raise ValueError("Choose a storage folder without control characters.")
    return '"' + str(value).replace('%', '%%').replace('\\', '\\\\').replace('"', '\\"') + '"'


class DownloadCancelled(Exception):
    pass


class ModelManager:
    def __init__(self, store):
        self.store = store
        self.engine = Path('/opt/sidekick/llama-server')
        self.stop = threading.Event()

    @property
    def storage(self):
        return Path(self.store.settings.get('model_folder', str(self.store.home / '.sidekick/models'))).expanduser().resolve()

    def install(self, model_id, progress, opener=urllib.request.urlopen):
        if model_id not in CATALOG:
            raise ValueError('Select one of the listed models.')
        if not self.engine.is_file() or not os.access(self.engine, os.X_OK):
            raise RuntimeError('The local AI engine is missing. This ISO needs the updated build files.')
        model = CATALOG[model_id]
        if memory_gib() and memory_gib() < model['minimum_ram_gib'] - 0.6:
            raise RuntimeError('This model needs more memory. Select a smaller model.')
        self.storage.mkdir(parents=True, exist_ok=True)
        destination = self.storage / model['filename']
        part = destination.with_suffix('.gguf.part')
        self.stop.clear()
        if destination.exists():
            progress('Checking the existing model…', 0)
            if self.checksum(destination) == model['sha256']:
                self.activate(model_id, destination, progress)
                return
            raise RuntimeError('The existing model failed its checksum. Choose an empty storage folder to download a clean copy.')
        offset = part.stat().st_size if part.exists() else 0
        if offset > model['bytes']:
            part.unlink(); offset = 0
        if shutil.disk_usage(self.storage).free < model['bytes'] - offset + 512 * 1024**2:
            raise RuntimeError('There is not enough free space in that folder. Choose another storage folder.')
        url = f"https://huggingface.co/{model['repo']}/resolve/{model['revision']}/{model['filename']}"
        if offset < model['bytes']:
            request = urllib.request.Request(url, headers={'Range': f'bytes={offset}-'} if offset else {})
            with opener(request, timeout=30) as response:
                if offset and response.status != 206:
                    offset = 0
                elif offset and not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                    raise RuntimeError('The download server returned an unexpected range. Try again.')
                with part.open('ab' if offset else 'wb') as output:
                    last = 0.0
                    while True:
                        if self.stop.is_set():
                            raise DownloadCancelled('Download paused. You can resume it from AI Setup.')
                        chunk = response.read(1024**2)
                        if not chunk:
                            break
                        if offset + len(chunk) > model['bytes']:
                            raise RuntimeError('The download was larger than the expected model.')
                        output.write(chunk); offset += len(chunk)
                        if time.monotonic() - last > 0.2:
                            progress(f"Downloading {model['name']} — {offset / 1024**3:.2f} / {model['bytes'] / 1024**3:.2f} GiB", offset / model['bytes'])
                            last = time.monotonic()
        if part.stat().st_size != model['bytes']:
            raise RuntimeError('The download was interrupted. Click Download again to resume.')
        progress('Verifying the completed download…', 1)
        if self.checksum(part) != model['sha256']:
            part.unlink()
            raise RuntimeError('The model checksum did not match. The corrupt download was discarded; try again.')
        os.replace(part, destination)
        self.activate(model_id, destination, progress)

    def checksum(self, path):
        digest = hashlib.sha256()
        with Path(path).open('rb') as f:
            for chunk in iter(lambda: f.read(4 * 1024**2), b''):
                if self.stop.is_set():
                    raise DownloadCancelled('Download check cancelled.')
                digest.update(chunk)
        return digest.hexdigest()

    def activate(self, model_id, destination, progress):
        if self.stop.is_set():
            raise DownloadCancelled('Setup cancelled before starting the model.')
        threads = max(1, min(os.cpu_count() or 2, 8))
        command = ' '.join([unit_quote(self.engine), '-m', unit_quote(destination),
                            '-c', '4096', '-t', str(threads), '--parallel', '1',
                            '--host', '127.0.0.1', '--port', '8080', '--jinja'])
        unit = ('[Unit]\nDescription=Sidekick local AI\n\n[Service]\n'
                'Type=simple\nExecStart=' + command + '\nRestart=on-failure\nRestartSec=5\n'
                'Nice=5\nNoNewPrivileges=true\n\n[Install]\nWantedBy=default.target\n')
        atomic_write(self.store.home / '.config/systemd/user/sidekick-ai.service', unit)
        self.store.configure(model_id=model_id, model_path=str(destination))
        for cmd in [['systemctl', '--user', 'daemon-reload'],
                    ['systemctl', '--user', 'enable', 'sidekick-ai.service'],
                    ['systemctl', '--user', 'restart', 'sidekick-ai.service']]:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=15)
        progress('Starting your local AI…', 1)
        for _ in range(120):
            if self.stop.is_set():
                raise DownloadCancelled('The model was installed. Its service is starting; check the status above.')
            if health():
                self.store.log('Set up AI', f'{CATALOG[model_id]["name"]}: verified and responding locally')
                progress('Your local AI is ready.', 1)
                return
            time.sleep(1)
        raise RuntimeError('The model is installed but has not become ready. Open Activity / AI logs for details.')

    def service(self, operation):
        if operation not in ('start', 'stop', 'restart'):
            raise ValueError('Unsupported model operation.')
        subprocess.run(['systemctl', '--user', operation, 'sidekick-ai.service'],
                       check=True, capture_output=True, text=True, timeout=15)
        self.store.log('AI ' + operation, 'Service command completed; readiness is checked separately.')


def stream_reply(domain, history, prompt, on_chunk, cancel, on_response=None, opener=urllib.request.urlopen):
    if domain not in DOMAINS:
        raise ValueError('Unknown conversation mode.')
    messages = [{'role': 'system', 'content': PERSONA + '\n' + DOMAINS[domain]}]
    messages += [{'role': x['role'], 'content': x['content'][:5000]} for x in history[-6:]]
    messages.append({'role': 'user', 'content': prompt[:12000]})
    data = json.dumps({'model': 'local', 'messages': messages, 'stream': True,
                       'temperature': 0.65 if domain in ('Music', 'Animation') else 0.3,
                       'max_tokens': 1800, 'chat_template_kwargs': {'enable_thinking': False}}).encode()
    request = urllib.request.Request(API + '/v1/chat/completions', data=data,
                                     headers={'Content-Type': 'application/json'})
    parts = []
    with opener(request, timeout=180) as response:
        if on_response:
            on_response(response)
        for line in response:
            if cancel.is_set():
                break
            if not line.startswith(b'data:'):
                continue
            raw = line[5:].strip()
            if raw == b'[DONE]':
                break
            try:
                event = json.loads(raw)
            except ValueError:
                continue
            if 'error' in event:
                raise RuntimeError(str(event['error']))
            choices = event.get('choices', [])
            if not choices:
                continue
            content = choices[0].get('delta', {}).get('content') or ''
            if content:
                parts.append(content); on_chunk(content)
    answer = ''.join(parts)
    if not answer and not cancel.is_set():
        raise RuntimeError('The local model returned no answer. Try a shorter question or restart it.')
    return answer
