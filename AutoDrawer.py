import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import pyautogui
import keyboard
import time
import cv2
import numpy as np
import math
import os            
import configparser  
import ctypes        
import sys           
from PIL import Image, ImageTk


class AutoSketchApp:
    def __init__(self, root):
        self.root = root
        self.root.title("杀戮尖塔2 自动素描机器人")
        self.root.geometry("520x750") 
        self.root.minsize(450, 400) 
        self.root.attributes("-topmost", True)

        self.is_running = False
        self.is_paused = False       
        self.stop_requested = False
        self.image_path = None
        self.contours = []
        self.image_size = (0, 0)
        self.config_file = "config.txt"  
        self.hotkey_handles = {}
        self.hotkey_current = {"start": "F9", "pause": "F8", "stop": "F10"}
        self.hotkey_capture_target = None
        self.hotkey_capture_backup = None

        self.setup_ui()
        self.load_config()               

        self.apply_hotkeys()
        self.root.bind("<KeyPress>", self.on_capture_keypress, add="+")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        style = ttk.Style()
        style.configure("TLabel", font=("Microsoft YaHei", 9))
        style.configure("TButton", font=("Microsoft YaHei", 10))

        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill="both", expand=True)

        self.main_canvas = tk.Canvas(self.main_frame, highlightthickness=0)
        self.main_canvas.pack(side="left", fill="both", expand=True)

        self.scrollbar = ttk.Scrollbar(self.main_frame, orient="vertical", command=self.main_canvas.yview)
        self.scrollbar.pack(side="right", fill="y")

        self.main_canvas.configure(yscrollcommand=self.scrollbar.set)

        self.content_frame = ttk.Frame(self.main_canvas)
        self.canvas_window = self.main_canvas.create_window((0, 0), window=self.content_frame, anchor="nw")

        self.content_frame.bind("<Configure>", lambda e: self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all")))
        self.main_canvas.bind("<Configure>", lambda e: self.main_canvas.itemconfig(self.canvas_window, width=e.width))
        self.root.bind_all("<MouseWheel>", lambda e: self.main_canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # --- 第一部分：图片加载与预览 ---
        img_frame = ttk.LabelFrame(self.content_frame, text=" 图片设置 (素描模式专用) ")
        img_frame.pack(fill="x", padx=15, pady=5)

        ttk.Button(img_frame, text="📁 选择并上传图片", command=self.load_image).pack(pady=5)

        self.preview_canvas = tk.Canvas(img_frame, width=300, height=200, bg="black")
        self.preview_canvas.pack(pady=5)
        self.preview_label = ttk.Label(img_frame, text="等待上传图片...", foreground="gray")
        self.preview_label.pack()

        detail_frame = ttk.Frame(img_frame)
        detail_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(detail_frame, text="线条细节(阈值):").grid(row=0, column=0, sticky="w", pady=2)
        self.threshold_var = tk.IntVar(value=100)
        thresh_spin = ttk.Spinbox(detail_frame, from_=10, to=200, textvariable=self.threshold_var, width=5, command=self.update_preview)
        thresh_spin.grid(row=0, column=2, padx=(0, 5))
        thresh_spin.bind('<Return>', self.update_preview)
        thresh_scale = ttk.Scale(detail_frame, from_=10, to=200, variable=self.threshold_var, orient="horizontal")
        thresh_scale.grid(row=0, column=1, sticky="ew", padx=5)
        thresh_scale.bind("<ButtonRelease-1>", self.update_preview)

        ttk.Label(detail_frame, text="过滤短线(防噪点):").grid(row=1, column=0, sticky="w", pady=2)
        self.min_len_var = tk.IntVar(value=10) 
        minlen_spin = ttk.Spinbox(detail_frame, from_=0, to=100, textvariable=self.min_len_var, width=5, command=self.update_preview)
        minlen_spin.grid(row=1, column=2, padx=(0, 5))
        minlen_spin.bind('<Return>', self.update_preview)
        minlen_scale = ttk.Scale(detail_frame, from_=0, to=100, variable=self.min_len_var, orient="horizontal")
        minlen_scale.grid(row=1, column=1, sticky="ew", padx=5)
        minlen_scale.bind("<ButtonRelease-1>", self.update_preview)
        
        detail_frame.columnconfigure(1, weight=1)

        # --- 第二部分：绘图区域设置 ---
        area_frame = ttk.LabelFrame(self.content_frame, text=" 绘制区域 (红框范围 %) ")
        area_frame.pack(fill="x", padx=15, pady=5)

        ttk.Label(area_frame, text="左侧避开%:").grid(row=0, column=0, padx=5, pady=5)
        self.left_margin = tk.IntVar(value=16)
        ttk.Spinbox(area_frame, from_=0, to=50, textvariable=self.left_margin, width=5).grid(row=0, column=1)

        ttk.Label(area_frame, text="右侧避开%:").grid(row=0, column=2, padx=5, pady=5)
        self.right_margin = tk.IntVar(value=19)
        ttk.Spinbox(area_frame, from_=0, to=50, textvariable=self.right_margin, width=5).grid(row=0, column=3)

        ttk.Label(area_frame, text="顶部避开%:").grid(row=1, column=0, padx=5, pady=5)
        self.top_margin = tk.IntVar(value=9)
        ttk.Spinbox(area_frame, from_=0, to=50, textvariable=self.top_margin, width=5).grid(row=1, column=1)

        ttk.Label(area_frame, text="底部避开%:").grid(row=1, column=2, padx=5, pady=5)
        self.bottom_margin = tk.IntVar(value=7)
        ttk.Spinbox(area_frame, from_=0, to=50, textvariable=self.bottom_margin, width=5).grid(row=1, column=3)

        ttk.Button(area_frame, text="✂️ 手动框选作画区域", command=self.start_area_selection).grid(row=2, column=0, columnspan=4, pady=(10, 5))

        # --- 第三部分：绘制参数 ---
        draw_frame = ttk.LabelFrame(self.content_frame, text=" 绘制参数 & 模式 ")
        draw_frame.pack(fill="x", padx=15, pady=5)

        ttk.Label(draw_frame, text="拖拽步长(像素):").grid(row=0, column=0, padx=10, pady=5, sticky="e")
        self.drag_step_var = tk.IntVar(value=5)  
        ttk.Spinbox(draw_frame, from_=1, to=50, textvariable=self.drag_step_var, width=8).grid(row=0, column=1)

        ttk.Label(draw_frame, text="起落笔延迟 (秒):").grid(row=1, column=0, padx=10, pady=5, sticky="e")
        self.delay_var = tk.DoubleVar(value=0.02)
        ttk.Spinbox(draw_frame, from_=0.00, to=0.2, increment=0.01, textvariable=self.delay_var, width=8).grid(row=1, column=1)

        ttk.Label(draw_frame, text="使用按键:").grid(row=0, column=2, padx=10, pady=5, sticky="e")
        self.btn_var = tk.StringVar(value="right")
        ttk.Combobox(draw_frame, textvariable=self.btn_var, values=["left", "right"], width=5, state="readonly").grid(row=0, column=3)

        self.auto_align_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(draw_frame, text="暂停恢复时自动寻找并物理对齐地图", variable=self.auto_align_var).grid(row=2, column=0, columnspan=4, padx=10, pady=5, sticky="w")

        # ★ 新增：第四部分 - 迷雾战场专属设置
        mist_frame = ttk.LabelFrame(self.content_frame, text=" 迷雾战场专属设置 (自定义大小与速度) ")
        mist_frame.pack(fill="x", padx=15, pady=5)

        ttk.Label(mist_frame, text="涂抹外扩大小(像素):").grid(row=0, column=0, padx=10, pady=5, sticky="e")
        self.mist_margin_var = tk.IntVar(value=40)
        ttk.Spinbox(mist_frame, from_=0, to=200, textvariable=self.mist_margin_var, width=8).grid(row=0, column=1)

        ttk.Label(mist_frame, text="涂抹线间距(越小越密):").grid(row=1, column=0, padx=10, pady=5, sticky="e")
        self.mist_spacing_var = tk.IntVar(value=3)
        ttk.Spinbox(mist_frame, from_=1, to=20, textvariable=self.mist_spacing_var, width=8).grid(row=1, column=1)

        ttk.Label(mist_frame, text="涂抹步幅(越大越快):").grid(row=2, column=0, padx=10, pady=5, sticky="e")
        self.mist_step_var = tk.IntVar(value=20)
        ttk.Spinbox(mist_frame, from_=5, to=150, textvariable=self.mist_step_var, width=8).grid(row=2, column=1)

        # ★ 新增：允许用户自定义单次向下滚动的距离
        ttk.Label(mist_frame, text="单次下滚距离(像素):").grid(row=3, column=0, padx=10, pady=5, sticky="e")
        self.mist_scroll_var = tk.IntVar(value=1200)
        ttk.Spinbox(mist_frame, from_=500, to=3000, increment=100, textvariable=self.mist_scroll_var, width=8).grid(row=3, column=1)

        # --- ????? ---
        hotkey_frame = ttk.LabelFrame(self.content_frame, text=" 快捷键设置 ")
        hotkey_frame.pack(fill="x", padx=15, pady=5)
        hotkey_frame.columnconfigure(1, weight=1)

        ttk.Label(hotkey_frame, text="开始:").grid(row=0, column=0, padx=10, pady=5, sticky="e")
        self.hotkey_start_var = tk.StringVar(value="F9")
        ttk.Entry(hotkey_frame, textvariable=self.hotkey_start_var, width=12, state="readonly").grid(row=0, column=1, padx=(0, 10), pady=5, sticky="w")
        ttk.Button(hotkey_frame, text="修改", command=lambda: self.start_hotkey_capture("start")).grid(row=0, column=2, padx=(0, 10), pady=5, sticky="w")

        ttk.Label(hotkey_frame, text="暂停/继续:").grid(row=1, column=0, padx=10, pady=5, sticky="e")
        self.hotkey_pause_var = tk.StringVar(value="F8")
        ttk.Entry(hotkey_frame, textvariable=self.hotkey_pause_var, width=12, state="readonly").grid(row=1, column=1, padx=(0, 10), pady=5, sticky="w")
        ttk.Button(hotkey_frame, text="修改", command=lambda: self.start_hotkey_capture("pause")).grid(row=1, column=2, padx=(0, 10), pady=5, sticky="w")

        ttk.Label(hotkey_frame, text="停止:").grid(row=2, column=0, padx=10, pady=5, sticky="e")
        self.hotkey_stop_var = tk.StringVar(value="F10")
        ttk.Entry(hotkey_frame, textvariable=self.hotkey_stop_var, width=12, state="readonly").grid(row=2, column=1, padx=(0, 10), pady=5, sticky="w")
        ttk.Button(hotkey_frame, text="修改", command=lambda: self.start_hotkey_capture("stop")).grid(row=2, column=2, padx=(0, 10), pady=5, sticky="w")

        ttk.Label(hotkey_frame, text="点击“修改”后直接按键，Esc 取消", foreground="gray").grid(row=3, column=0, columnspan=3, padx=10, pady=(0, 5), sticky="w")

        # ★ 独立功能区 - 迷雾战场
        mist_btn = ttk.Button(self.content_frame, text="🌫️ 迷雾战场 (全自动探索并涂抹图标)", command=self.on_btn_mist)
        mist_btn.pack(pady=(15, 0))

        ttk.Button(self.content_frame, text="💾 保存当前所有设置至配置文件", command=self.save_all_to_config).pack(pady=(10, 0))

        # --- 状态与控制 ---
        self.hotkey_hint_label = ttk.Label(self.content_frame, text=self.get_hotkey_hint_text(), foreground="red",
                                           font=("Microsoft YaHei", 10, "bold"))
        self.hotkey_hint_label.pack(pady=10)
        self.status_label = ttk.Label(self.content_frame, text="当前状态: 待机中...", font=("Microsoft YaHei", 11, "bold"),
                                      foreground="blue")
        self.status_label.pack(pady=5)

    def get_hotkey_hint_text(self):
        start = self.hotkey_current.get("start", "F9")
        pause = self.hotkey_current.get("pause", "F8")
        stop = self.hotkey_current.get("stop", "F10")
        return f"{start}: 开始素描 | {pause}: 暂停/继续 | {stop}: 停止"

    def update_hotkey_label(self):
        if hasattr(self, "hotkey_hint_label"):
            self.hotkey_hint_label.config(text=self.get_hotkey_hint_text())

    def _hk(self, key, fallback):
        return self.hotkey_current.get(key, fallback)

    def _normalize_hotkey(self, value, default):
        text = (value or "").strip()
        return text if text else default

    def _event_to_hotkey(self, event):
        key = (event.keysym or "").lower()
        if not key:
            return None
        if key in {"shift_l", "shift_r", "control_l", "control_r", "alt_l", "alt_r"}:
            return None

        alias = {
            "return": "enter",
            "prior": "page up",
            "next": "page down",
            "caps_lock": "caps lock",
            "num_lock": "num lock",
            "scroll_lock": "scroll lock",
            "print": "print screen",
        }

        key_name = alias.get(key, key)
        modifiers = []
        if event.state & 0x0004:
            modifiers.append("ctrl")
        if event.state & 0x0008:
            modifiers.append("alt")
        if event.state & 0x0001:
            modifiers.append("shift")

        return "+".join(modifiers + [key_name])

    def start_hotkey_capture(self, target):
        if self.hotkey_capture_target is not None:
            return

        self.hotkey_capture_target = target
        self.hotkey_capture_backup = {
            "start": self.hotkey_start_var.get(),
            "pause": self.hotkey_pause_var.get(),
            "stop": self.hotkey_stop_var.get(),
            "current": dict(self.hotkey_current),
        }

        self._clear_hotkeys()
        labels = {"start": "开始", "pause": "暂停/继续", "stop": "停止"}
        self.status_label.config(
            text=f"正在设置“{labels.get(target, target)}”快捷键：请按键（Esc 取消）",
            foreground="purple"
        )
        self.root.focus_force()

    def on_capture_keypress(self, event):
        if self.hotkey_capture_target is None:
            return None

        key = (event.keysym or "").lower()
        if key in {"escape", "esc"}:
            self.cancel_hotkey_capture()
            return "break"

        hotkey = self._event_to_hotkey(event)
        if not hotkey:
            return "break"

        target = self.hotkey_capture_target
        target_var = {
            "start": self.hotkey_start_var,
            "pause": self.hotkey_pause_var,
            "stop": self.hotkey_stop_var,
        }[target]
        target_var.set(hotkey)

        applied = self.apply_hotkeys()
        self.hotkey_capture_target = None
        self.hotkey_capture_backup = None
        if applied:
            self.status_label.config(text=f"快捷键已更新：{self.get_hotkey_hint_text()}", foreground="green")
        return "break"

    def cancel_hotkey_capture(self):
        if self.hotkey_capture_target is None or not self.hotkey_capture_backup:
            return

        backup = self.hotkey_capture_backup
        self.hotkey_start_var.set(backup["start"])
        self.hotkey_pause_var.set(backup["pause"])
        self.hotkey_stop_var.set(backup["stop"])
        old = backup["current"]
        self._set_hotkeys(old.get("start", "F9"), old.get("pause", "F8"), old.get("stop", "F10"))

        self.hotkey_capture_target = None
        self.hotkey_capture_backup = None
        self.status_label.config(text="已取消快捷键修改", foreground="blue")

    def _clear_hotkeys(self):
        for handle in getattr(self, "hotkey_handles", {}).values():
            try:
                keyboard.remove_hotkey(handle)
            except Exception:
                pass
        self.hotkey_handles = {}

    def _reset_hotkey_vars(self, values):
        self.hotkey_start_var.set(values["start"])
        self.hotkey_pause_var.set(values["pause"])
        self.hotkey_stop_var.set(values["stop"])

    def _set_hotkeys(self, start, pause, stop):
        self._clear_hotkeys()
        try:
            h_start = keyboard.add_hotkey(start, self.on_hotkey_start)
            h_pause = keyboard.add_hotkey(pause, self.on_hotkey_pause)
            h_stop = keyboard.add_hotkey(stop, self.on_hotkey_stop)
        except Exception as e:
            self._clear_hotkeys()
            return False, e

        self.hotkey_handles = {"start": h_start, "pause": h_pause, "stop": h_stop}
        self.hotkey_current = {"start": start, "pause": pause, "stop": stop}
        self.update_hotkey_label()
        return True, None

    def apply_hotkeys(self):
        old = dict(self.hotkey_current)

        new_start = self._normalize_hotkey(self.hotkey_start_var.get(), old.get("start", "F9"))
        new_pause = self._normalize_hotkey(self.hotkey_pause_var.get(), old.get("pause", "F8"))
        new_stop = self._normalize_hotkey(self.hotkey_stop_var.get(), old.get("stop", "F10"))

        if len({new_start.lower(), new_pause.lower(), new_stop.lower()}) < 3:
            messagebox.showwarning("快捷键冲突", "开始/暂停/停止的快捷键不能重复。")
            self._reset_hotkey_vars(old)
            return False

        ok, err = self._set_hotkeys(new_start, new_pause, new_stop)
        if ok:
            return True

        messagebox.showerror("快捷键设置失败", f"无法注册快捷键: {err}")
        self._set_hotkeys(old.get("start", "F9"), old.get("pause", "F8"), old.get("stop", "F10"))
        self._reset_hotkey_vars(old)
        return False

    def load_config(self):
        if not os.path.exists(self.config_file):
            self.create_default_config()

        config = configparser.ConfigParser()
        try:
            config.read(self.config_file, encoding='utf-8')
            self.threshold_var.set(config.getint('线条设置', 'threshold', fallback=self.threshold_var.get()))
            self.min_len_var.set(config.getint('线条设置', 'min_len', fallback=self.min_len_var.get()))
            
            self.left_margin.set(config.getint('绘制区域', 'left_margin', fallback=self.left_margin.get()))
            self.right_margin.set(config.getint('绘制区域', 'right_margin', fallback=self.right_margin.get()))
            self.top_margin.set(config.getint('绘制区域', 'top_margin', fallback=self.top_margin.get()))
            self.bottom_margin.set(config.getint('绘制区域', 'bottom_margin', fallback=self.bottom_margin.get()))
            
            self.drag_step_var.set(config.getint('绘制参数', 'drag_step', fallback=self.drag_step_var.get()))
            self.delay_var.set(config.getfloat('绘制参数', 'delay', fallback=self.delay_var.get()))
            self.btn_var.set(config.get('绘制参数', 'mouse_btn', fallback=self.btn_var.get()))
            self.auto_align_var.set(config.getboolean('绘制参数', 'auto_align', fallback=self.auto_align_var.get()))
            
            # ★ 新增：读取迷雾专属设置
            self.mist_margin_var.set(config.getint('迷雾设置', 'mist_margin', fallback=self.mist_margin_var.get()))
            self.mist_spacing_var.set(config.getint('迷雾设置', 'mist_spacing', fallback=self.mist_spacing_var.get()))
            self.mist_step_var.set(config.getint('迷雾设置', 'mist_step', fallback=self.mist_step_var.get()))
            # ★ 读取滚动距离配置
            self.mist_scroll_var.set(config.getint('迷雾设置', 'mist_scroll', fallback=self.mist_scroll_var.get()))
            self.hotkey_start_var.set(config.get('快捷键', 'start', fallback=self.hotkey_start_var.get()))
            self.hotkey_pause_var.set(config.get('快捷键', 'pause', fallback=self.hotkey_pause_var.get()))
            self.hotkey_stop_var.set(config.get('快捷键', 'stop', fallback=self.hotkey_stop_var.get()))
        except Exception as e:
            print(f"配置文件读取有误: {e}")

    def create_default_config(self):
        default_content = """# ==========================================
# 杀戮尖塔2自动素描机器人 - 本地配置文件
# ==========================================

[线条设置]
threshold = 100
min_len = 10

[绘制区域]
left_margin = 16
right_margin = 19
top_margin = 9
bottom_margin = 7

[绘制参数]
drag_step = 5
delay = 0.02
mouse_btn = right
auto_align = True
[快捷键]
start = F9
pause = F8
stop = F10


[迷雾设置]
mist_margin = 40
mist_spacing = 3
mist_step = 20
mist_scroll = 1200"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                f.write(default_content)
        except: pass

    def save_all_to_config(self):
        # ★ 重构了写入逻辑，现在可以直接覆盖式刷新整个文档，绝不会丢失参数
        content = f"""# ==========================================
# 杀戮尖塔2自动素描机器人 - 本地配置文件
# ==========================================

[线条设置]
threshold = {self.threshold_var.get()}
min_len = {self.min_len_var.get()}

[绘制区域]
left_margin = {self.left_margin.get()}
right_margin = {self.right_margin.get()}
top_margin = {self.top_margin.get()}
bottom_margin = {self.bottom_margin.get()}

[绘制参数]
drag_step = {self.drag_step_var.get()}
delay = {self.delay_var.get()}
mouse_btn = {self.btn_var.get()}
auto_align = {self.auto_align_var.get()}
[快捷键]
start = {self.hotkey_current.get("start", "F9")}
pause = {self.hotkey_current.get("pause", "F8")}
stop = {self.hotkey_current.get("stop", "F10")}


[迷雾设置]
mist_margin = {self.mist_margin_var.get()}
mist_spacing = {self.mist_spacing_var.get()}
mist_step = {self.mist_step_var.get()}
mist_scroll = {self.mist_scroll_var.get()}"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                f.write(content)
            messagebox.showinfo("保存成功", "当前所有的参数设置已成功保存至 config.txt！")
        except Exception as e:
            messagebox.showerror("保存失败", f"保存配置失败: {e}")

    def start_area_selection(self):
        self.root.withdraw()
        time.sleep(0.2) 
        self.overlay = tk.Toplevel()
        self.overlay.attributes('-fullscreen', True)
        self.overlay.attributes('-alpha', 0.4) 
        self.overlay.attributes('-topmost', True)
        self.overlay.config(bg='black', cursor="crosshair") 

        self.overlay_canvas = tk.Canvas(self.overlay, bg="black", highlightthickness=0)
        self.overlay_canvas.pack(fill="both", expand=True)

        self.sel_rect = None
        self.start_x = 0
        self.start_y = 0

        self.overlay_canvas.bind("<ButtonPress-1>", self.on_selection_start)
        self.overlay_canvas.bind("<B1-Motion>", self.on_selection_drag)
        self.overlay_canvas.bind("<ButtonRelease-1>", self.on_selection_end)
        self.overlay.bind("<Escape>", self.cancel_selection)   
        self.overlay.bind("<Button-3>", self.cancel_selection) 

    def cancel_selection(self, event=None):
        self.overlay.destroy()
        self.root.deiconify() 

    def on_selection_start(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.sel_rect:
            self.overlay_canvas.delete(self.sel_rect)
        self.sel_rect = self.overlay_canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline="red", width=3)

    def on_selection_drag(self, event):
        self.overlay_canvas.coords(self.sel_rect, self.start_x, self.start_y, event.x, event.y)

    def on_selection_end(self, event):
        end_x, end_y = event.x, event.y
        screen_w = self.overlay.winfo_width()
        screen_h = self.overlay.winfo_height()
        self.overlay.destroy()
        self.root.deiconify() 

        x1, x2 = min(self.start_x, end_x), max(self.start_x, end_x)
        y1, y2 = min(self.start_y, end_y), max(self.start_y, end_y)

        if x2 - x1 < 50 or y2 - y1 < 50:
            messagebox.showwarning("提示", "框选范围太小，已取消修改。")
            return

        left_pct = int((x1 / screen_w) * 100)
        right_pct = int(((screen_w - x2) / screen_w) * 100)
        top_pct = int((y1 / screen_h) * 100)
        bottom_pct = int(((screen_h - y2) / screen_h) * 100)

        self.left_margin.set(max(0, min(50, left_pct)))
        self.right_margin.set(max(0, min(50, right_pct)))
        self.top_margin.set(max(0, min(50, top_pct)))
        self.bottom_margin.set(max(0, min(50, bottom_pct)))
        messagebox.showinfo("提示", "绘制区域已更新！\n（如需永久保留此设置，请点击主界面底部的“保存”按钮）")

    def load_image(self):
        file_path = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp")])
        if file_path:
            self.image_path = file_path
            self.update_preview()
            self.status_label.config(text="当前状态: 准备就绪", foreground="green")

    def update_preview(self, *args):
        if not self.image_path: return
        img = cv2.imdecode(np.fromfile(self.image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None: return

        self.image_size = (img.shape[1], img.shape[0])
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        thresh1 = self.threshold_var.get()
        thresh2 = thresh1 * 2
        edges = cv2.Canny(gray, thresh1, thresh2)

        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        raw_contours = []
        min_len = self.min_len_var.get()
        
        for c in contours:
            if cv2.arcLength(c, True) < min_len: continue
            epsilon = 0.001 * cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, epsilon, False)
            if len(approx) > 1: raw_contours.append(approx)

        self.contours = []
        if raw_contours:
            unvisited = list(raw_contours)
            current_point = (0, 0)
            while unvisited:
                best_idx = 0
                min_dist = float('inf')
                reverse_best = False
                for i, contour in enumerate(unvisited):
                    start_pt = contour[0][0]
                    end_pt = contour[-1][0]
                    dist_to_start = (start_pt[0] - current_point[0]) ** 2 + (start_pt[1] - current_point[1]) ** 2
                    dist_to_end = (end_pt[0] - current_point[0]) ** 2 + (end_pt[1] - current_point[1]) ** 2
                    if dist_to_start < min_dist:
                        min_dist, best_idx, reverse_best = dist_to_start, i, False
                    if dist_to_end < min_dist:
                        min_dist, best_idx, reverse_best = dist_to_end, i, True
                best_contour = unvisited.pop(best_idx)
                if reverse_best: best_contour = best_contour[::-1]
                self.contours.append(best_contour)
                current_point = best_contour[-1][0]

        preview_img = Image.fromarray(edges)
        preview_img.thumbnail((300, 200), Image.Resampling.LANCZOS)
        self.tk_img = ImageTk.PhotoImage(preview_img)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(150, 100, anchor="center", image=self.tk_img)
        self.preview_label.config(text=f"解析完成：高质量提取 {len(self.contours)} 条路径段")

    def on_hotkey_start(self):
        if not self.is_running and self.contours:
            self.start_drawing()

    def on_hotkey_pause(self):
        if self.is_running and not self.stop_requested:
            self.is_paused = not self.is_paused

    def on_hotkey_stop(self):
        if self.is_running:
            self.stop_requested = True
            self.is_paused = False  
            self.status_label.config(text="正在强制停止...", foreground="orange")

    # ==========================================
    # ★ 迷雾战场核心功能区 (回滚至稳定版高通滤波，放弃宝箱换取绝对准确率)
    # ==========================================
    def on_btn_mist(self):
        if not self.is_running:
            self.is_running = True
            self.is_paused = False
            self.stop_requested = False
            self.status_label.config(text=f"迷雾战场启动中! ({self._hk('stop', 'F10')}停止)", foreground="red")
            threading.Thread(target=self.mist_mode_task, daemon=True).start()

    def mist_mode_task(self):
        pyautogui.PAUSE = 0
        screen_w, screen_h = pyautogui.size()
        box_x = screen_w * (self.left_margin.get() / 100.0)
        box_y = screen_h * (self.top_margin.get() / 100.0)
        box_w = screen_w * (1 - self.left_margin.get() / 100.0 - self.right_margin.get() / 100.0)
        box_h = screen_h * (1 - self.top_margin.get() / 100.0 - self.bottom_margin.get() / 100.0)

        delay = max(0.015, self.delay_var.get())
        btn = self.btn_var.get()
        
        painted_nodes = []
        global_screen_y = 0  

        # ★ 新增：迷雾战场专属的暂停与物理对齐检查函数
        def check_mist_pause(resume_x=None, resume_y=None, resume_down=False):
            if not self.is_paused:
                return True

            pyautogui.mouseUp(button=btn)

            if self.auto_align_var.get():
                self.root.after(0, lambda: self.status_label.config(text="正在保存地图锚点快照...", foreground="purple"))
                aw, ah = int(box_w * 0.50), int(box_h * 0.50)
                ax, ay = int(box_x + (box_w - aw) / 2), int(box_y + (box_h - ah) / 2)
                anchor_img = pyautogui.screenshot(region=(ax, ay, aw, ah))
                anchor_cv = cv2.cvtColor(np.array(anchor_img), cv2.COLOR_RGB2BGR)
                old_rel_x = ax - box_x
                old_rel_y = ay - box_y

            self.root.after(0, lambda: self.status_label.config(text=f"迷雾战场: 已暂停 (按{self._hk('pause', 'F8')}继续)", foreground="purple"))
            
            while self.is_paused and not self.stop_requested:
                time.sleep(0.1)
                
            if self.stop_requested:
                return False

            if self.auto_align_var.get():
                self.root.after(0, lambda: self.status_label.config(text="正在大范围扫描寻找对齐点...", foreground="orange"))
                found = False
                
                scroll_sweeps = [0] + [800] * 5 + [-800] * 10 + [800] * 5
                for sc in scroll_sweeps:
                    if self.stop_requested: break
                    if sc != 0:
                        pyautogui.moveTo(box_x + box_w / 2, box_y + box_h / 2)
                        pyautogui.scroll(sc)
                        time.sleep(0.4)

                    screen_img = pyautogui.screenshot(region=(int(box_x), int(box_y), int(box_w), int(box_h)))
                    screen_cv = cv2.cvtColor(np.array(screen_img), cv2.COLOR_RGB2BGR)
                    
                    res = cv2.matchTemplate(screen_cv, anchor_cv, cv2.TM_CCOEFF_NORMED)
                    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                    
                    if max_val > 0.80: 
                        found = True
                        break
                        
                if found:
                    self.root.after(0, lambda: self.status_label.config(text="目标已锁定，正在物理精准拖拽...", foreground="orange"))
                    for _ in range(5):
                        if self.stop_requested: break
                        screen_img = pyautogui.screenshot(region=(int(box_x), int(box_y), int(box_w), int(box_h)))
                        screen_cv = cv2.cvtColor(np.array(screen_img), cv2.COLOR_RGB2BGR)
                        res = cv2.matchTemplate(screen_cv, anchor_cv, cv2.TM_CCOEFF_NORMED)
                        _, max_val, _, max_loc = cv2.minMaxLoc(res)
                        
                        if max_val < 0.5: break 
                            
                        dx = max_loc[0] - old_rel_x
                        dy = max_loc[1] - old_rel_y
                        
                        if abs(dx) <= 2 and abs(dy) <= 2:
                            break
                            
                        pyautogui.moveTo(box_x + box_w / 2, box_y + box_h / 2)
                        pyautogui.mouseDown(button='left')
                        time.sleep(0.05)
                        pyautogui.move(-dx, -dy, duration=0.2)
                        time.sleep(0.05)
                        pyautogui.mouseUp(button='left')
                        time.sleep(0.3) 
                else:
                    messagebox.showwarning("对齐失败", "未能找回原位置，迷雾涂抹可能会出现少许遗漏！")

            self.root.after(0, lambda: self.status_label.config(text="迷雾战场: 正在全屏极致遮盖...", foreground="red"))
            
            if resume_x is not None and resume_y is not None:
                pyautogui.moveTo(resume_x, resume_y, duration=0.01)
                time.sleep(delay)
                if resume_down:
                    pyautogui.mouseDown(button=btn)
                    time.sleep(delay)
                    
            return True

        self.root.after(0, lambda: self.status_label.config(text="正在获取焦点并导航至顶端...", foreground="orange"))
        
        pyautogui.click(box_x + box_w/2, box_y + box_h/2, button='right')
        time.sleep(0.2)
        
        # 狂暴上滚确保登顶
        for _ in range(40):
            if self.stop_requested: return
            if not check_mist_pause(): return # ★ 检查暂停
            pyautogui.scroll(800)
            time.sleep(0.05)
        time.sleep(0.5) 

        self.root.after(0, lambda: self.status_label.config(text="迷雾战场: 正在全屏极致遮盖...", foreground="red"))

        # ★ 新增参数 is_end：用于标记是否已经到了地图绝对底部
        def scan_and_paint(screen_cv, is_end=False):
            gray = cv2.cvtColor(screen_cv, cv2.COLOR_BGR2GRAY)
            
            blur = cv2.GaussianBlur(gray, (55, 55), 0)
            diff = cv2.subtract(blur, gray)
            
            _, thresh = cv2.threshold(diff, 15, 255, cv2.THRESH_BINARY)

            kernel_open = np.ones((7, 7), np.uint8)
            opened = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_open)

            kernel_close = np.ones((15, 15), np.uint8)
            blobs = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel_close)
            blobs = cv2.dilate(blobs, kernel_close, iterations=1)

            contours, _ = cv2.findContours(blobs, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for c in contours:
                if self.stop_requested: break
                if not check_mist_pause(): break # ★ 检查暂停
                
                x, y, w, h = cv2.boundingRect(c)
                area = cv2.contourArea(c)
                
                if 30 <= w <= 250 and 30 <= h <= 250:
                    aspect_ratio = float(w) / h if h > 0 else 0
                    if 0.4 <= aspect_ratio <= 2.5:
                        fill_ratio = area / (w * h)
                        if fill_ratio > 0.3:
                            
                            # ★ 核心防漏脚修复：如果图标碰到了扫描框的最底部，说明它被截断了！
                            # 只要还没滚到绝对底部，我们就跳过它，等下一次滚动把它完全带入屏幕中央再画！
                            if not is_end and (y + h > box_h - 15):
                                continue

                            cx = x + w // 2
                            cy = y + h // 2
                            
                            global_cx = cx
                            global_cy = global_screen_y + cy

                            already_painted = False
                            for (px, py) in painted_nodes:
                                if math.hypot(global_cx - px, global_cy - py) < 80:
                                    already_painted = True
                                    break

                            if not already_painted:
                                painted_nodes.append((global_cx, global_cy))

                                target_x = box_x + cx
                                target_y = box_y + cy

                                pyautogui.moveTo(target_x, target_y)
                                time.sleep(0.3) 
                                pyautogui.mouseDown(button=btn)
                                time.sleep(delay)

                                # ★ 动态获取你在 UI 或 Config 设定的迷雾参数
                                paint_radius = int(max(w, h) * 0.55) + self.mist_margin_var.get()
                                ring_spacing = self.mist_spacing_var.get()
                                theta = 0.0
                                
                                while True:
                                    r = ring_spacing * (theta / (2 * math.pi))
                                    if r > paint_radius:
                                        break
                                        
                                    px = target_x + r * math.cos(theta)
                                    py = target_y + r * math.sin(theta)
                                    
                                    if self.stop_requested: break
                                    if not check_mist_pause(px, py, True): break # ★ 检查画圈过程中的暂停
                                    
                                    pyautogui.moveTo(px, py)
                                    
                                    time.sleep(0.001) 
                                    
                                    # 利用你在 UI 中调整的步幅（速度）
                                    d_theta = float(self.mist_step_var.get()) / max(r, 5.0)
                                    theta += d_theta

                                pyautogui.mouseUp(button=btn)
                                time.sleep(delay)

        # 初始满屏全盘扫描
        if check_mist_pause(): # ★ 检查开局暂停
            screen_img = pyautogui.screenshot(region=(int(box_x), int(box_y), int(box_w), int(box_h)))
            screen_cv = cv2.cvtColor(np.array(screen_img), cv2.COLOR_RGB2BGR)
            scan_and_paint(screen_cv, is_end=False)

        # 边滚边扫，直至侦测到底部边界
        while not self.stop_requested:
            if not check_mist_pause(): break # ★ 检查滚动间隔的暂停
            
            anchor_h = int(box_h * 0.4)
            anchor_y = int(box_y + box_h - anchor_h)
            anchor_img = pyautogui.screenshot(region=(int(box_x), anchor_y, int(box_w), anchor_h))
            anchor_cv = cv2.cvtColor(np.array(anchor_img), cv2.COLOR_RGB2BGR)
            old_rel_y = box_h - anchor_h

            pyautogui.moveTo(box_x + box_w/2, box_y + box_h/2)
            # ★ 使用用户自定义的下滚距离
            pyautogui.scroll(-self.mist_scroll_var.get()) 
            time.sleep(0.6) 

            new_screen = pyautogui.screenshot(region=(int(box_x), int(box_y), int(box_w), int(box_h)))
            new_cv = cv2.cvtColor(np.array(new_screen), cv2.COLOR_RGB2BGR)

            res = cv2.matchTemplate(new_cv, anchor_cv, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)

            if max_val < 0.7:
                # 锚点大变样（进Boss或其他），强制当做最后一次扫描
                scan_and_paint(new_cv, is_end=True)
                break

            new_rel_y = max_loc[1]
            dy = old_rel_y - new_rel_y 

            if dy <= 10: 
                # ★ 触底了！进行最后一次清算，把之前卡在底边的半截图标全涂了
                scan_and_paint(new_cv, is_end=True)
                break

            global_screen_y += dy 
            scan_and_paint(new_cv, is_end=False)

        pyautogui.mouseUp(button=btn)
        self.root.after(0, lambda: self.status_label.config(text="迷雾战场：极致无缝涂抹完毕！", foreground="green"))
        self.root.after(2000, self.reset_ui)

    # ==========================================
    # 常规素描核心功能区
    # ==========================================
    def start_drawing(self):
        self.is_running = True
        self.is_paused = False
        self.stop_requested = False
        self.status_label.config(
            text=f"正在作画中! ({self._hk('pause', 'F8')}暂停 | {self._hk('stop', 'F10')}停止)",
            foreground="red"
        )
        threading.Thread(target=self.draw_task, daemon=True).start()

    def draw_task(self):
        pyautogui.PAUSE = 0
        screen_w, screen_h = pyautogui.size()

        box_x = screen_w * (self.left_margin.get() / 100.0)
        box_y = screen_h * (self.top_margin.get() / 100.0)
        box_w = screen_w * (1 - self.left_margin.get() / 100.0 - self.right_margin.get() / 100.0)
        box_h = screen_h * (1 - self.top_margin.get() / 100.0 - self.bottom_margin.get() / 100.0)

        img_w, img_h = self.image_size
        if img_w == 0 or img_h == 0:
            self.root.after(0, self.reset_ui)
            return

        scale = min(box_w / img_w, box_h / img_h)
        draw_w = img_w * scale
        draw_h = img_h * scale
        offset_x = box_x + (box_w - draw_w) / 2
        offset_y = box_y + (box_h - draw_h) / 2

        step_px = max(1, self.drag_step_var.get())
        delay = max(0.015, self.delay_var.get())
        mouse_btn = self.btn_var.get()

        self.global_offset_x = 0
        self.global_offset_y = 0

        def check_pause(target_x, target_y, should_be_down):
            if not self.is_paused:
                return True, 0, 0

            old_gx = self.global_offset_x
            old_gy = self.global_offset_y

            pyautogui.mouseUp(button=mouse_btn)

            if self.auto_align_var.get():
                self.root.after(0, lambda: self.status_label.config(text="正在保存地图锚点快照...", foreground="purple"))
                aw, ah = int(box_w * 0.50), int(box_h * 0.50)
                ax, ay = int(box_x + (box_w - aw) / 2), int(box_y + (box_h - ah) / 2)
                anchor_img = pyautogui.screenshot(region=(ax, ay, aw, ah))
                anchor_cv = cv2.cvtColor(np.array(anchor_img), cv2.COLOR_RGB2BGR)
                old_rel_x = ax - box_x
                old_rel_y = ay - box_y

            self.root.after(0, lambda: self.status_label.config(text=f"当前状态: 已暂停 (按{self._hk('pause', 'F8')}继续)", foreground="purple"))
            
            while self.is_paused and not self.stop_requested:
                time.sleep(0.1)
                
            if self.stop_requested:
                return False, 0, 0

            if self.auto_align_var.get():
                self.root.after(0, lambda: self.status_label.config(text="正在大范围扫描寻找对齐点...", foreground="orange"))
                found = False
                
                scroll_sweeps = [0] + [800] * 5 + [-800] * 10 + [800] * 5
                for sc in scroll_sweeps:
                    if self.stop_requested: break
                    if sc != 0:
                        pyautogui.moveTo(box_x + box_w / 2, box_y + box_h / 2)
                        pyautogui.scroll(sc)
                        time.sleep(0.4)

                    screen_img = pyautogui.screenshot(region=(int(box_x), int(box_y), int(box_w), int(box_h)))
                    screen_cv = cv2.cvtColor(np.array(screen_img), cv2.COLOR_RGB2BGR)
                    
                    res = cv2.matchTemplate(screen_cv, anchor_cv, cv2.TM_CCOEFF_NORMED)
                    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                    
                    if max_val > 0.80: 
                        found = True
                        break
                        
                if found:
                    self.root.after(0, lambda: self.status_label.config(text="目标已锁定，正在物理精准拖拽...", foreground="orange"))
                    dx, dy = 0, 0
                    for _ in range(5):
                        if self.stop_requested: break
                        screen_img = pyautogui.screenshot(region=(int(box_x), int(box_y), int(box_w), int(box_h)))
                        screen_cv = cv2.cvtColor(np.array(screen_img), cv2.COLOR_RGB2BGR)
                        res = cv2.matchTemplate(screen_cv, anchor_cv, cv2.TM_CCOEFF_NORMED)
                        _, max_val, _, max_loc = cv2.minMaxLoc(res)
                        
                        if max_val < 0.5: break 
                            
                        dx = max_loc[0] - old_rel_x
                        dy = max_loc[1] - old_rel_y
                        
                        if abs(dx) <= 2 and abs(dy) <= 2:
                            dx, dy = 0, 0 
                            break
                            
                        pyautogui.moveTo(box_x + box_w / 2, box_y + box_h / 2)
                        pyautogui.mouseDown(button='left')
                        time.sleep(0.05)
                        pyautogui.move(-dx, -dy, duration=0.2)
                        time.sleep(0.05)
                        pyautogui.mouseUp(button='left')
                        time.sleep(0.3) 
                        
                    self.global_offset_x += dx
                    self.global_offset_y += dy
                else:
                    messagebox.showwarning("对齐失败", "滚动搜索未能找回原位置，将在当前位置继续强行绘制。")
            
            self.root.after(
                0,
                lambda: self.status_label.config(
                    text=f"正在作画中! ({self._hk('pause', 'F8')}暂停 | {self._hk('stop', 'F10')}停止)",
                    foreground="red"
                )
            )
            
            delta_x = self.global_offset_x - old_gx
            delta_y = self.global_offset_y - old_gy

            new_target_x = target_x + delta_x
            new_target_y = target_y + delta_y
            
            pyautogui.moveTo(new_target_x, new_target_y, duration=0.01)
            time.sleep(delay)
            if should_be_down:
                pyautogui.mouseDown(button=mouse_btn)
                time.sleep(delay)
                
            return True, delta_x, delta_y

        try:
            pyautogui.mouseUp(button=mouse_btn)
            time.sleep(delay)

            for contour in self.contours:
                if self.stop_requested: break

                first_point = True
                prev_x, prev_y = 0, 0
                for point in contour:
                    if self.stop_requested: break

                    img_x, img_y = point[0]
                    screen_x = int(offset_x + img_x * scale) + self.global_offset_x
                    screen_y = int(offset_y + img_y * scale) + self.global_offset_y

                    if first_point:
                        ok, d_x, d_y = check_pause(screen_x, screen_y, False)
                        if not ok: break
                        if d_x != 0 or d_y != 0:
                            screen_x += d_x
                            screen_y += d_y

                        pyautogui.mouseUp(button=mouse_btn)
                        time.sleep(delay) 
                        
                        pyautogui.moveTo(screen_x, screen_y, duration=0.01) 
                        time.sleep(delay) 

                        pyautogui.mouseDown(button=mouse_btn)
                        time.sleep(delay) 
                        
                        first_point = False
                        prev_x, prev_y = screen_x, screen_y
                    else:
                        dist = math.hypot(screen_x - prev_x, screen_y - prev_y)
                        steps = int(dist / step_px)
                        if steps < 1: steps = 1

                        for i in range(1, steps + 1):
                            if self.stop_requested: break
                            nx = prev_x + (screen_x - prev_x) * (i / steps)
                            ny = prev_y + (screen_y - prev_y) * (i / steps)
                            
                            ok, d_x, d_y = check_pause(int(nx), int(ny), True)
                            if not ok: break
                            
                            if d_x != 0 or d_y != 0:
                                screen_x += d_x
                                screen_y += d_y
                                prev_x += d_x
                                prev_y += d_y
                                nx += d_x
                                ny += d_y

                            pyautogui.moveTo(int(nx), int(ny))
                            if self.drag_step_var.get() < 20:
                                time.sleep(0.001)

                        prev_x, prev_y = screen_x, screen_y

                pyautogui.mouseUp(button=mouse_btn)
                time.sleep(delay)

        finally:
            pyautogui.mouseUp(button=mouse_btn)
            self.root.after(0, self.reset_ui)

    def reset_ui(self):
        self.is_running = False
        self.is_paused = False
        self.status_label.config(text="当前状态: 待机中...", foreground="blue")

    def on_closing(self):
        self.stop_requested = True
        keyboard.unhook_all()
        self.root.destroy()


if __name__ == "__main__":
    def is_admin():
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    if is_admin():
        root = tk.Tk()
        app = AutoSketchApp(root)
        root.mainloop()
    else:
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit()
