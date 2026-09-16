#!/usr/bin/env python3
"""Boot the built live system in a disposable VM with no disks or network."""
import argparse
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import time

p=argparse.ArgumentParser();p.add_argument('iso');p.add_argument('--log',default='boot-smoke.log')
a=p.parse_args();iso=Path(a.iso).resolve();log=Path(a.log).resolve()
with tempfile.TemporaryDirectory(prefix='sidekick-boot-') as temp:
    temp=Path(temp)
    for item in ('vmlinuz','initrd.img'):
        subprocess.run(['xorriso','-osirrox','on','-indev',str(iso),'-extract','/live/'+item,str(temp/item)],check=True)
    accel='kvm' if os.access('/dev/kvm',os.R_OK|os.W_OK) else 'tcg'
    command=['qemu-system-x86_64','-machine','accel='+accel,'-cpu','max','-m','4096','-smp','2',
             '-display','none','-vga','std','-serial','stdio','-monitor','none','-no-reboot','-nic','none',
             '-cdrom',str(iso),'-kernel',str(temp/'vmlinuz'),'-initrd',str(temp/'initrd.img'),
             '-append','boot=live components username=hacker user-fullname=Sidekick hostname=sidekick '
                       'noeject console=tty0 console=ttyS0 sidekick.selftest=1']
    with log.open('w') as output:
        proc=subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT)
        deadline=time.monotonic()+480
        try:
            while proc.poll() is None and time.monotonic()<deadline:
                time.sleep(1)
            if proc.poll() is None:
                proc.terminate();proc.wait(timeout=10)
                raise SystemExit('Boot smoke test timed out. See '+str(log))
        finally:
            if proc.poll() is None:proc.kill();proc.wait()
    content=log.read_text(errors='replace')
    if 'SIDEKICK_BOOT_OK' not in content:
        print(content[-18000:]);raise SystemExit('The live desktop failed its boot test.')
    print('SIDEKICK_BOOT_OK: live user, XFCE window manager and companion stayed running.')
