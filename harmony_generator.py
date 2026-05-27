"""
ハモリジェネレーター
メロディMIDIを読み込み、ダイアトニックハモリのMIDIを生成する
"""

import os
import sys
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from collections import defaultdict

try:
    import mido
    from mido import MidiFile, MidiTrack, Message
except ImportError:
    mido = None

# ─── 音楽理論定数 ────────────────────────────────────────────
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

SCALES = {
    'major': [0, 2, 4, 5, 7, 9, 11],
    'minor': [0, 2, 3, 5, 7, 8, 10],
}

HARMONY_OPTIONS = {
    '3度上（定番・明るめ）': 2,
    '6度上（ふわっと・柔らか）': 5,
    '3度下（落ち着き・渋め）': -2,
    '5度上（力強い・厚め）': 4,
}


# ─── ハモリ生成ロジック ──────────────────────────────────────
def build_scale(root: str, scale_type: str) -> list:
    """指定キー・スケールの全MIDIノート番号リストを返す"""
    root_num = NOTE_NAMES.index(root)
    intervals = SCALES[scale_type]
    notes = []
    for octave in range(11):
        for interval in intervals:
            n = octave * 12 + root_num + interval
            if 0 <= n <= 127:
                notes.append(n)
    return sorted(set(notes))


def find_harmony_note(melody_note: int, scale: list, steps: int):
    """スケール内でsteps度上/下のノートを返す。スケール外音は最近傍に丸める"""
    if melody_note in scale:
        idx = scale.index(melody_note)
    else:
        idx = min(range(len(scale)), key=lambda i: abs(scale[i] - melody_note))

    target = idx + steps
    if 0 <= target < len(scale):
        return scale[target]
    return None


def generate_harmony_midi(input_path: str, output_path: str,
                           root: str, scale_type: str, steps: int):
    mid = MidiFile(input_path)
    scale = build_scale(root, scale_type)

    out = MidiFile(type=1, ticks_per_beat=mid.ticks_per_beat)

    for track in mid.tracks:
        out.tracks.append(track)  # 元トラックをそのまま保持

        # ノートを含まないトラック（テンポ情報のみ等）はスキップ
        has_notes = any(msg.type in ('note_on', 'note_off') for msg in track)
        if not has_notes:
            continue

        # ─ absolute timeに変換して処理 ─
        abs_events = []
        abs_t = 0
        for msg in track:
            abs_t += msg.time
            abs_events.append((abs_t, msg))

        harm_events = []
        note_stack = defaultdict(list)  # 和音にも対応できるようリストで管理

        for abs_t, msg in abs_events:
            is_note_on = msg.type == 'note_on' and msg.velocity > 0
            is_note_off = msg.type == 'note_off' or (
                msg.type == 'note_on' and msg.velocity == 0)

            if is_note_on:
                h = find_harmony_note(msg.note, scale, steps)
                if h is not None:
                    note_stack[msg.note].append(h)
                    harm_events.append((abs_t, Message(
                        'note_on', channel=msg.channel,
                        note=h,
                        velocity=max(1, int(msg.velocity * 0.75)),
                        time=0
                    )))
            elif is_note_off:
                stack = note_stack.get(msg.note, [])
                if stack:
                    h = stack.pop(0)
                    harm_events.append((abs_t, Message(
                        'note_off', channel=msg.channel,
                        note=h, velocity=0, time=0
                    )))
            else:
                # テンポ・拍子等はそのままコピー
                harm_events.append((abs_t, msg.copy(time=0)))

        # delta timeに戻してトラックに追加
        harm_track = MidiTrack()
        prev_t = 0
        for abs_t, msg in sorted(harm_events, key=lambda x: x[0]):
            delta = abs_t - prev_t
            harm_track.append(msg.copy(time=delta))
            prev_t = abs_t

        out.tracks.append(harm_track)

    out.save(output_path)


# ─── GUI ────────────────────────────────────────────────────
class App:
    def __init__(self, root_widget):
        self.root = root_widget
        root_widget.title('ハモリジェネレーター')
        root_widget.resizable(False, False)

        pad = {'padx': 12, 'pady': 7}

        # ── MIDIファイル選択 ──
        tk.Label(root_widget, text='メロディMIDI:').grid(
            row=0, column=0, sticky='w', **pad)
        self.midi_var = tk.StringVar()
        tk.Entry(root_widget, textvariable=self.midi_var, width=38).grid(
            row=0, column=1, **pad)
        tk.Button(root_widget, text='参照…', command=self.browse).grid(
            row=0, column=2, **pad)

        # ── キー ──
        tk.Label(root_widget, text='キー:').grid(
            row=1, column=0, sticky='w', **pad)
        self.key_var = tk.StringVar(value='C')
        ttk.Combobox(root_widget, textvariable=self.key_var,
                     values=NOTE_NAMES, width=6, state='readonly').grid(
            row=1, column=1, sticky='w', **pad)

        # ── スケール ──
        tk.Label(root_widget, text='スケール:').grid(
            row=2, column=0, sticky='w', **pad)
        self.scale_var = tk.StringVar(value='major')
        frame_s = tk.Frame(root_widget)
        frame_s.grid(row=2, column=1, sticky='w', **pad)
        tk.Radiobutton(frame_s, text='メジャー',
                       variable=self.scale_var, value='major').pack(side='left')
        tk.Radiobutton(frame_s, text='マイナー',
                       variable=self.scale_var, value='minor').pack(side='left')

        # ── ハモリタイプ ──
        tk.Label(root_widget, text='ハモリ:').grid(
            row=3, column=0, sticky='w', **pad)
        self.harm_var = tk.StringVar(value=list(HARMONY_OPTIONS.keys())[0])
        ttk.Combobox(root_widget, textvariable=self.harm_var,
                     values=list(HARMONY_OPTIONS.keys()),
                     width=30, state='readonly').grid(row=3, column=1, **pad)

        # ── 生成ボタン ──
        tk.Button(root_widget, text='ハモリを生成する',
                  command=self.generate,
                  bg='#4a9eff', fg='white',
                  font=('', 11, 'bold'),
                  height=2, width=22).grid(
            row=4, column=0, columnspan=3, pady=16)

        # ── ステータス ──
        self.status_var = tk.StringVar(value='MIDIファイルを選択してください')
        tk.Label(root_widget, textvariable=self.status_var,
                 fg='gray').grid(row=5, column=0, columnspan=3, padx=12, pady=4)

    def browse(self):
        path = filedialog.askopenfilename(
            filetypes=[('MIDI files', '*.mid *.midi'), ('All files', '*.*')])
        if path:
            self.midi_var.set(path)
            self.status_var.set(f'読み込み: {os.path.basename(path)}')

    def generate(self):
        if mido is None:
            messagebox.showerror(
                'エラー',
                'mido がインストールされていません。\n'
                'コマンドプロンプトで以下を実行してください:\n\n'
                'pip install mido'
            )
            return

        path = self.midi_var.get()
        if not path or not os.path.exists(path):
            messagebox.showwarning('注意', 'MIDIファイルを選択してください')
            return

        root_note = self.key_var.get()
        scale_type = self.scale_var.get()
        steps = HARMONY_OPTIONS[self.harm_var.get()]

        base, ext = os.path.splitext(path)
        output_path = base + '_harmony' + ext

        try:
            self.status_var.set('生成中…')
            self.root.update()
            generate_harmony_midi(path, output_path, root_note, scale_type, steps)
            self.status_var.set(f'完成 → {os.path.basename(output_path)}')
            messagebox.showinfo(
                '完了',
                f'ハモリMIDIを保存しました:\n{output_path}\n\n'
                'DAWにドラッグ＆ドロップして使ってください'
            )
        except Exception as e:
            messagebox.showerror('エラー', f'生成に失敗しました:\n{e}')
            self.status_var.set('エラーが発生しました')


# ─── エントリポイント ────────────────────────────────────────
def ensure_mido():
    """mido が入っていなければ自動でインストールする"""
    try:
        import mido  # noqa: F401
    except ImportError:
        import subprocess
        print('mido をインストールしています…')
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'mido'])


if __name__ == '__main__':
    ensure_mido()

    import importlib
    import mido as _mido  # noqa: F811
    globals()['mido'] = _mido
    from mido import MidiFile, MidiTrack, Message  # noqa: F811

    win = tk.Tk()
    App(win)
    win.mainloop()
