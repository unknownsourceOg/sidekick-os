"""Create a standard MIDI sketch with independent chords, bass and drums."""
import json
from pathlib import Path
import struct

KEYS = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'Bb': 10}
STYLES = ('Country swing', 'Hip-hop', 'Rock', 'Ambient')
TPQ = 480


def vlq(value):
    if value < 0:
        raise ValueError('Negative MIDI delta.')
    out = [value & 127]
    value >>= 7
    while value:
        out.insert(0, (value & 127) | 128)
        value >>= 7
    return bytes(out)


def track(events, end):
    data = bytearray(); last = 0
    for tick, event in sorted(events, key=lambda x: (x[0], 0 if x[1][0] & 0xf0 == 0x80 else 1)):
        data += vlq(tick - last) + event; last = tick
    data += vlq(max(0, end - last)) + b'\xff\x2f\x00'
    return b'MTrk' + struct.pack('>I', len(data)) + data


def note(events, channel, pitch, start, duration, velocity=80):
    events.append((start, bytes((0x90 + channel, pitch, velocity))))
    events.append((start + duration, bytes((0x80 + channel, pitch, 0))))


def make_sketch(folder, key='C', bpm=110, style='Country swing', bars=8):
    if key not in KEYS or style not in STYLES or not 40 <= bpm <= 220 or not 4 <= bars <= 32:
        raise ValueError('Choose a supported key/style, 40–220 BPM and 4–32 bars.')
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / 'starter.mid'
    if out.exists():
        raise FileExistsError('A sketch already exists in this project.')
    end = bars * TPQ * 4
    tempo = round(60000000 / bpm)
    conductor = [(0, b'\xff\x51\x03' + tempo.to_bytes(3, 'big')),
                 (0, b'\xff\x58\x04\x04\x02\x18\x08')]
    chords = [(0, bytes((0xc0, 24 if style == 'Country swing' else 0)))]
    bass = [(0, bytes((0xc1, 32)))]
    drums = []
    progression = [(0, (0, 4, 7)), (7, (0, 4, 7)), (9, (0, 3, 7)), (5, (0, 4, 7))]
    for bar in range(bars):
        offset = bar * TPQ * 4
        root, intervals = progression[bar % 4]
        root += KEYS[key]
        for interval in intervals:
            note(chords, 0, 60 + root + interval, offset, TPQ * 4 - 30, 62)
        for beat in (0, 2):
            note(bass, 1, 36 + root, offset + beat * TPQ, TPQ - 30, 78)
        if style != 'Ambient':
            for beat in range(4):
                note(drums, 9, 36 if beat % 2 == 0 else 38, offset + beat * TPQ, 80, 95)
                note(drums, 9, 42, offset + beat * TPQ, 50, 56)
                swing = 320 if style == 'Country swing' else 240
                note(drums, 9, 42, offset + beat * TPQ + swing, 50, 40)
    data = b'MThd' + struct.pack('>IHHH', 6, 1, 4, TPQ)
    data += b''.join(track(events, end) for events in (conductor, chords, bass, drums))
    out.write_bytes(data)
    (folder / 'project.json').write_text(json.dumps({'key': key, 'bpm': bpm, 'style': style,
                                                   'bars': bars, 'progression': 'I–V–vi–IV'}, indent=2))
    (folder / 'START-HERE.txt').write_text(
        f'{style} MIDI sketch • {key} major • {bpm} BPM • {bars} bars\n\n'
        'Import starter.mid into LMMS or your DAW. Assign instruments to chords, bass and drums.\n'
        'This is an editable MIDI sketch, not a recorded performance or finished song.\n'
        'Ask Sidekick in Music mode for melody, lyrics, arrangement or mixing help.\n')
    return out
