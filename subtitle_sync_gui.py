#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字幕时间轴对齐工具 GUI v2.0
Subtitle Timeline Sync Tool
"""

import re
import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

# ─────────────────────────────────────────────
# Time Parsing & Formatting
# ─────────────────────────────────────────────

def parse_user_time(text: str) -> float:
    text = text.strip().lower().replace(',', '.')
    m = re.match(r'^(\d+(?:\.\d+)?)\s*s?$', text)
    if m: return float(m.group(1))
    m = re.match(r'^(\d+):(\d+(?:\.\d+)?)$', text)
    if m: return int(m.group(1)) * 60 + float(m.group(2))
    m = re.match(r'^(\d+):(\d+):(\d+(?:\.\d+)?)$', text)
    if m: return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    m = re.match(r'^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?$', text)
    if m and any(m.groups()):
        return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + float(m.group(3) or 0)
    raise ValueError(f"无法解析时间: '{text}'")

def secs_to_display(total_secs: float) -> str:
    if total_secs < 0: total_secs = 0.0
    h = int(total_secs // 3600)
    m = int((total_secs % 3600) // 60)
    s = total_secs % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:06.3f}"
    return f"{m:02d}:{s:06.3f}"

def secs_to_srt(total_secs: float) -> str:
    if total_secs < 0: total_secs = 0.0
    h = int(total_secs // 3600)
    m = int((total_secs % 3600) // 60)
    s = int(total_secs % 60)
    ms = int(round((total_secs - int(total_secs)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def secs_to_ass(total_secs: float) -> str:
    if total_secs < 0: total_secs = 0.0
    h = int(total_secs // 3600)
    m = int((total_secs % 3600) // 60)
    s = int(total_secs % 60)
    cs = int(round((total_secs - int(total_secs)) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def srt_to_secs(ts: str) -> float:
    ts = ts.strip().replace(',', '.')
    m = re.match(r'(\d+):(\d+):(\d+)\.(\d+)', ts)
    if m:
        return int(m.group(1))*3600 + int(m.group(2))*60 + int(m.group(3)) + int(m.group(4).ljust(3,'0')[:3])/1000
    raise ValueError(f"Invalid SRT ts: {ts}")

def ass_to_secs(ts: str) -> float:
    ts = ts.strip()
    m = re.match(r'(\d+):(\d+):(\d+)\.(\d+)', ts)
    if m:
        return int(m.group(1))*3600 + int(m.group(2))*60 + int(m.group(3)) + int(m.group(4).ljust(2,'0')[:2])/100
    raise ValueError(f"Invalid ASS ts: {ts}")

def format_offset(secs: float) -> str:
    sign = '+' if secs >= 0 else '-'
    a = abs(secs)
    if a < 60: return f"{sign}{a:.3f}s"
    m = int(a // 60)
    s = a % 60
    return f"{sign}{m}m{s:.3f}s"

# ─────────────────────────────────────────────
# Subtitle Processing
# ─────────────────────────────────────────────

def parse_srt(content):
    content = content.replace('\r\n','\n').replace('\r','\n')
    blocks = re.split(r'\n\s*\n', content.strip())
    entries = []
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 2: continue
        ts_line = ts_idx = None
        for i, line in enumerate(lines):
            if '-->' in line:
                ts_line, ts_idx = line, i
                break
        if ts_line is None: continue
        m = re.match(r'([\d:,\.]+)\s*-->\s*([\d:,\.]+)', ts_line)
        if not m: continue
        start, end = srt_to_secs(m.group(1)), srt_to_secs(m.group(2))
        text = '\n'.join(lines[ts_idx+1:]).strip()
        entries.append({'start': start, 'end': end, 'text': text})
    return entries

def build_srt(entries, offset):
    lines = []
    for i, e in enumerate(entries, 1):
        lines.append(str(i))
        lines.append(f"{secs_to_srt(e['start']+offset)} --> {secs_to_srt(e['end']+offset)}")
        lines.append(e['text'])
        lines.append('')
    return '\n'.join(lines)

def process_ass(content, offset):
    lines = content.replace('\r\n','\n').replace('\r','\n').split('\n')
    result = []
    pat = re.compile(
        r'^((?:Dialogue|Comment):\s*\d+,\s*)'
        r'(\d+:\d+:\d+\.\d+)(\s*,\s*)(\d+:\d+:\d+\.\d+)(,.*)', re.I)
    for line in lines:
        m = pat.match(line)
        if m:
            s = ass_to_secs(m.group(2)) + offset
            e = ass_to_secs(m.group(4)) + offset
            result.append(f"{m.group(1)}{secs_to_ass(s)}{m.group(3)}{secs_to_ass(e)}{m.group(5)}")
        else:
            result.append(line)
    return '\n'.join(result)

def get_ass_dialogues(content):
    lines = content.replace('\r\n','\n').replace('\r','\n').split('\n')
    entries = []
    pat = re.compile(r'^Dialogue:\s*\d+,\s*(\d+:\d+:\d+\.\d+)\s*,\s*(\d+:\d+:\d+\.\d+)\s*,(.*)', re.I)
    for line in lines:
        m = pat.match(line)
        if m:
            start, end = ass_to_secs(m.group(1)), ass_to_secs(m.group(2))
            parts = m.group(3).split(',', 8)
            text = parts[-1].strip() if parts else m.group(3)
            text = re.sub(r'\{[^}]*\}', '', text).replace('\\N',' ').replace('\\n',' ').strip()
            if text:
                entries.append({'start': start, 'end': end, 'text': text})
    return entries

# ─────────────────────────────────────────────
# File Helpers
# ─────────────────────────────────────────────

VIDEO_EXTS = {'.mp4','.mkv','.avi','.mov','.wmv','.flv','.ts','.m4v','.webm','.mpg','.mpeg','.rmvb','.rm','.m2ts'}
SUB_EXTS = {'.srt','.ass','.ssa'}

def detect_encoding(filepath):
    for enc in ['utf-8-sig','utf-8','utf-16','gb18030','gbk','gb2312','big5','shift_jis','euc-jp','euc-kr','latin-1']:
        try:
            with open(filepath, 'r', encoding=enc) as f: f.read()
            return enc
        except (UnicodeDecodeError, UnicodeError): continue
    return 'utf-8'

def read_file(filepath):
    enc = detect_encoding(filepath)
    with open(filepath, 'r', encoding=enc) as f: return f.read()


# ─────────────────────────────────────────────
# GUI Application
# ─────────────────────────────────────────────

class SubtitleSyncApp:
    def __init__(self, root):
        self.root = root
        self.root.title("字幕时间轴对齐工具")
        self.root.geometry("800x780")
        self.root.minsize(700, 700)

        # State
        self.video_path = None
        self.sub_path = None
        self.sub_content = None
        self.sub_ext = None
        self.entries = []
        self.selected_index = 0
        self.current_secs = 0.0
        self.has_time = False

        # Style
        style = ttk.Style()
        try:
            style.theme_use('aqua')
        except:
            style.theme_use('clam')

        style.configure('Title.TLabel', font=('Helvetica', 20, 'bold'))
        style.configure('Subtitle.TLabel', font=('Helvetica', 12), foreground='#666')
        style.configure('Section.TLabel', font=('Helvetica', 13, 'bold'))
        style.configure('Path.TLabel', font=('Menlo', 11), foreground='#2196F3')
        style.configure('Status.TLabel', font=('Helvetica', 12), foreground='#4CAF50')
        style.configure('Big.TButton', font=('Helvetica', 13), padding=(20, 10))
        style.configure('Action.TButton', font=('Helvetica', 14, 'bold'), padding=(30, 12))
        style.configure('TimeDisplay.TLabel', font=('Menlo', 28, 'bold'))
        style.configure('Offset.TLabel', font=('Menlo', 12), foreground='#666')

        self.build_ui()

        # Enable drag-and-drop via Tk DnD or manual drop
        self._setup_dnd()

    def _setup_dnd(self):
        """Setup file drag-and-drop. Files can be dragged onto the entry fields."""
        # On macOS, we can intercept command-line-style drops via binding
        # The entry fields accept pasted/dropped paths
        pass

    def build_ui(self):
        main = ttk.Frame(self.root, padding=20)
        main.pack(fill=tk.BOTH, expand=True)

        # ── Title ──
        ttk.Label(main, text="字幕时间轴对齐工具", style='Title.TLabel').pack(pady=(0, 2))
        ttk.Label(main, text="Subtitle Timeline Sync", style='Subtitle.TLabel').pack(pady=(0, 15))
        ttk.Separator(main, orient='horizontal').pack(fill=tk.X, pady=5)

        # ── Step 1: Video ──
        f1 = ttk.LabelFrame(main, text="❶ 视频文件（用于获取文件名和输出路径）", padding=10)
        f1.pack(fill=tk.X, pady=(10, 5))

        row1 = ttk.Frame(f1)
        row1.pack(fill=tk.X)
        ttk.Button(row1, text="选择视频…", command=self.pick_video).pack(side=tk.LEFT)

        self.video_entry = ttk.Entry(row1, width=55, font=('Menlo', 11))
        self.video_entry.pack(side=tk.LEFT, padx=(10, 0), fill=tk.X, expand=True)
        self.video_entry.insert(0, "拖入视频文件到此处，或点击选择")
        self.video_entry.config(foreground='#999')
        self.video_entry.bind('<FocusIn>', lambda e: self._clear_placeholder(self.video_entry, "拖入视频文件到此处，或点击选择"))
        self.video_entry.bind('<FocusOut>', lambda e: self._restore_placeholder(self.video_entry, "拖入视频文件到此处，或点击选择"))
        self.video_entry.bind('<Return>', lambda e: self._accept_video_from_entry())

        self.video_status = ttk.Label(f1, text="", foreground='#4CAF50')
        self.video_status.pack(anchor='w', pady=(4, 0))

        # ── Step 2: Subtitle ──
        f2 = ttk.LabelFrame(main, text="❷ 字幕文件（.srt / .ass，拖入或选择）", padding=10)
        f2.pack(fill=tk.X, pady=5)

        row2 = ttk.Frame(f2)
        row2.pack(fill=tk.X)
        ttk.Button(row2, text="选择字幕…", command=self.pick_subtitle).pack(side=tk.LEFT)

        self.sub_entry = ttk.Entry(row2, width=55, font=('Menlo', 11))
        self.sub_entry.pack(side=tk.LEFT, padx=(10, 0), fill=tk.X, expand=True)
        self.sub_entry.insert(0, "拖入字幕文件到此处，或点击选择")
        self.sub_entry.config(foreground='#999')
        self.sub_entry.bind('<FocusIn>', lambda e: self._clear_placeholder(self.sub_entry, "拖入字幕文件到此处，或点击选择"))
        self.sub_entry.bind('<FocusOut>', lambda e: self._restore_placeholder(self.sub_entry, "拖入字幕文件到此处，或点击选择"))
        self.sub_entry.bind('<Return>', lambda e: self._accept_sub_from_entry())

        self.sub_status = ttk.Label(f2, text="", foreground='#4CAF50')
        self.sub_status.pack(anchor='w', pady=(4, 0))

        # ── Step 3: Dialogue List ──
        f3 = ttk.LabelFrame(main, text="❸ 点击选择用于对齐的对白", padding=10)
        f3.pack(fill=tk.BOTH, expand=True, pady=5)

        columns = ('index', 'time', 'text')
        self.tree = ttk.Treeview(f3, columns=columns, show='headings', height=10, selectmode='browse')
        self.tree.heading('index', text='#')
        self.tree.heading('time', text='时间')
        self.tree.heading('text', text='对白内容')
        self.tree.column('index', width=40, minwidth=40, stretch=False, anchor='center')
        self.tree.column('time', width=90, minwidth=90, stretch=False, anchor='center')
        self.tree.column('text', width=520, minwidth=200)

        scrollbar = ttk.Scrollbar(f3, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind('<<TreeviewSelect>>', self.on_select_dialogue)

        # ── Step 4: Time Input + Stepper ──
        f4 = ttk.LabelFrame(main, text="❹ 该对白在影片中出现的时间", padding=10)
        f4.pack(fill=tk.X, pady=5)

        # Large time display
        self.time_display = ttk.Label(f4, text="00:00.000", style='TimeDisplay.TLabel', anchor='center')
        self.time_display.pack(fill=tk.X, pady=(0, 8))

        # Input row
        input_row = ttk.Frame(f4)
        input_row.pack()

        ttk.Label(input_row, text="输入时间:").pack(side=tk.LEFT, padx=(0, 5))
        self.time_entry = ttk.Entry(input_row, width=18, font=('Menlo', 13), justify='center')
        self.time_entry.pack(side=tk.LEFT, padx=(0, 8))
        self.time_entry.bind('<KeyRelease>', self._on_time_key)
        self.time_entry.bind('<Return>', self._on_time_key)
        ttk.Label(input_row, text="(20 / 1:30 / 1m30s)", foreground='#999').pack(side=tk.LEFT)

        # Stepper buttons
        stepper_row = ttk.Frame(f4)
        stepper_row.pack(pady=(10, 4))

        btn_data = [
            ("−1s",    -1.0),
            ("−100ms", -0.1),
            ("+100ms", +0.1),
            ("+1s",    +1.0),
        ]
        for label, delta in btn_data:
            b = tk.Button(stepper_row, text=label, font=('Menlo', 11, 'bold'),
                         fg='#0071E3' if delta > 0 else '#FF9500',
                         bg='#F0F0F5', activebackground='#D0D0D8',
                         bd=0, padx=12, pady=5, highlightthickness=0,
                         command=lambda d=delta: self._step_time(d))
            b.pack(side=tk.LEFT, padx=3)

        # Offset display
        self.offset_label = ttk.Label(f4, text="", style='Offset.TLabel', anchor='center')
        self.offset_label.pack(fill=tk.X, pady=(6, 0))

        # ── Execute + Options ──
        bottom = ttk.Frame(main)
        bottom.pack(fill=tk.X, pady=(10, 5))

        self.run_btn = ttk.Button(bottom, text="▶  对齐并输出字幕", style='Action.TButton', command=self.execute)
        self.run_btn.pack()

        # Open video checkbox
        opts = ttk.Frame(main)
        opts.pack(pady=(2, 5))
        self.open_video_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="完成后打开视频播放", variable=self.open_video_var).pack()

        # Status
        self.status_var = tk.StringVar(value="")
        self.status_label = ttk.Label(main, textvariable=self.status_var, style='Status.TLabel', wraplength=700)
        self.status_label.pack(pady=(2, 0))

    # ── Placeholder helpers ──

    def _clear_placeholder(self, entry, placeholder):
        if entry.get() == placeholder:
            entry.delete(0, tk.END)
            entry.config(foreground='#000')

    def _restore_placeholder(self, entry, placeholder):
        if not entry.get().strip():
            entry.insert(0, placeholder)
            entry.config(foreground='#999')

    def _clean_path(self, p):
        p = p.strip()
        if (p.startswith('"') and p.endswith('"')) or (p.startswith("'") and p.endswith("'")):
            p = p[1:-1]
        p = re.sub(r'\\(.)', r'\1', p)
        return p.strip()

    # ── Accept files from entry fields (drag-and-drop paths) ──

    def _accept_video_from_entry(self):
        raw = self.video_entry.get().strip()
        path = self._clean_path(raw)
        if os.path.isfile(path):
            ext = Path(path).suffix.lower()
            if ext in VIDEO_EXTS:
                self._set_video(path)
            else:
                self.video_status.config(text=f"⚠ 非常见视频格式 ({ext})，仍将使用", foreground='#FF9500')
                self._set_video(path)
        else:
            self.video_status.config(text=f"✗ 文件不存在", foreground='red')

    def _accept_sub_from_entry(self):
        raw = self.sub_entry.get().strip()
        path = self._clean_path(raw)
        if os.path.isfile(path):
            ext = Path(path).suffix.lower()
            if ext in SUB_EXTS:
                self._set_subtitle(path)
            else:
                self.sub_status.config(text=f"✗ 不支持 {ext} 格式，需要 .srt/.ass", foreground='red')
        else:
            self.sub_status.config(text=f"✗ 文件不存在", foreground='red')

    # ── File Pickers ──

    def pick_video(self):
        exts = [('视频文件', ' '.join(f'*{e}' for e in sorted(VIDEO_EXTS))), ('所有文件', '*')]
        path = filedialog.askopenfilename(title="选择视频文件", filetypes=exts)
        if path:
            self._set_video(path)

    def _set_video(self, path):
        self.video_path = path
        name = Path(path).name
        # Update entry
        self.video_entry.delete(0, tk.END)
        self.video_entry.insert(0, path)
        self.video_entry.config(foreground='#000')
        self.video_status.config(text=f"✓ {name}", foreground='#4CAF50')

    def pick_subtitle(self):
        exts = [('字幕文件', '*.srt *.ass *.ssa'), ('所有文件', '*')]
        path = filedialog.askopenfilename(title="选择字幕文件", filetypes=exts)
        if path:
            self._set_subtitle(path)

    def _set_subtitle(self, path):
        ext = Path(path).suffix.lower()
        self.sub_path = path
        self.sub_ext = ext
        try:
            self.sub_content = read_file(path)
        except Exception as e:
            messagebox.showerror("读取失败", f"无法读取字幕文件:\n{e}")
            return

        name = Path(path).name
        self.sub_entry.delete(0, tk.END)
        self.sub_entry.insert(0, path)
        self.sub_entry.config(foreground='#000')
        self.sub_status.config(text=f"✓ {name}  ({ext.upper()[1:]})", foreground='#4CAF50')
        self.load_dialogues()

    def load_dialogues(self):
        self.tree.delete(*self.tree.get_children())
        self.entries = []

        if self.sub_ext == '.srt':
            self.entries = parse_srt(self.sub_content)
        else:
            self.entries = get_ass_dialogues(self.sub_content)

        if not self.entries:
            messagebox.showwarning("解析失败", "未能从字幕中解析出对白行")
            return

        count = min(10, len(self.entries))
        for i, e in enumerate(self.entries[:count]):
            ts = secs_to_display(e['start'])
            text = e['text'].replace('\n', ' ')
            if len(text) > 80: text = text[:77] + "…"
            self.tree.insert('', tk.END, iid=str(i), values=(f"{i+1}", ts, text))

        self.tree.selection_set('0')
        self.selected_index = 0
        self.status_var.set(f"已加载 {len(self.entries)} 条对白，显示前 {count} 条")

    def on_select_dialogue(self, event):
        sel = self.tree.selection()
        if sel:
            self.selected_index = int(sel[0])
            self._update_offset()

    # ── Time Stepper ──

    def _on_time_key(self, event=None):
        text = self.time_entry.get().strip()
        if text:
            try:
                secs = parse_user_time(text)
                self.current_secs = secs
                self.has_time = True
                self._update_time_display()
                self._update_offset()
            except ValueError:
                pass

    def _step_time(self, delta):
        if not self.has_time:
            # Try parsing current entry first
            text = self.time_entry.get().strip()
            if text:
                try:
                    self.current_secs = parse_user_time(text)
                    self.has_time = True
                except ValueError:
                    return
            else:
                return

        self.current_secs = max(0, self.current_secs + delta)
        self.has_time = True
        # Update entry to show new value
        self.time_entry.delete(0, tk.END)
        self.time_entry.insert(0, secs_to_display(self.current_secs))
        self._update_time_display()
        self._update_offset()

    def _update_time_display(self):
        if self.has_time:
            self.time_display.config(text=secs_to_display(self.current_secs), foreground='#1D1D1F')
        else:
            self.time_display.config(text="00:00.000", foreground='#CCC')

    def _update_offset(self):
        if not self.entries or not self.has_time:
            return
        source = self.entries[self.selected_index]['start']
        offset = self.current_secs - source
        ref_text = self.entries[self.selected_index]['text'][:30].replace('\n', ' ')
        self.offset_label.config(
            text=f"偏移: {format_offset(offset)}    (#{self.selected_index+1} 「{ref_text}」  {secs_to_display(source)} → {secs_to_display(self.current_secs)})")

    # ── Execute ──

    def execute(self):
        if not self.video_path:
            # Try entry field
            self._accept_video_from_entry()
        if not self.video_path or not os.path.isfile(self.video_path):
            messagebox.showwarning("提示", "请先选择或拖入视频文件")
            return

        if not self.sub_content:
            self._accept_sub_from_entry()
        if not self.sub_path or not self.sub_content:
            messagebox.showwarning("提示", "请先选择或拖入字幕文件")
            return
        if not self.entries:
            messagebox.showwarning("提示", "字幕中没有对白")
            return
        if not self.has_time:
            self._on_time_key()
        if not self.has_time:
            messagebox.showwarning("提示", "请输入对白在影片中的实际时间")
            return

        source = self.entries[self.selected_index]['start']
        offset = self.current_secs - source

        video_dir = os.path.dirname(self.video_path)
        video_name = Path(self.video_path).stem
        output_name = f"{video_name}{self.sub_ext}"
        output_path = os.path.join(video_dir, output_name)

        if os.path.exists(output_path):
            if not messagebox.askyesno("文件已存在", f"{output_name}\n已存在，是否覆盖？"):
                i = 1
                while os.path.exists(output_path):
                    output_name = f"{video_name}.synced{i}{self.sub_ext}"
                    output_path = os.path.join(video_dir, output_name)
                    i += 1

        try:
            if self.sub_ext == '.srt':
                result = build_srt(parse_srt(self.sub_content), offset)
            else:
                result = process_ass(self.sub_content, offset)
            with open(output_path, 'w', encoding='utf-8-sig') as f:
                f.write(result)
        except Exception as e:
            messagebox.showerror("处理失败", str(e))
            return

        self.status_var.set(f"✅ 已保存: {output_name}  |  偏移: {format_offset(offset)}  |  路径: {video_dir}")

        # Open video if checked
        if self.open_video_var.get():
            try:
                subprocess.Popen(['open', self.video_path])
            except:
                pass

        messagebox.showinfo("完成 ✓",
            f"字幕已对齐并保存！\n\n"
            f"📄 {output_name}\n"
            f"📁 {video_dir}\n"
            f"⏱ 偏移: {format_offset(offset)}")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    root = tk.Tk()
    if sys.platform == 'darwin':
        try:
            root.createcommand('tk::mac::Quit', root.destroy)
        except:
            pass
    SubtitleSyncApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()
