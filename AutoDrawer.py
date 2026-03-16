import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import pyautogui
import keyboard
import time
import cv2
import numpy as np
import math
import os            # ★ 新增导入 os 库，用于检测文件
import configparser  # ★ 新增导入 configparser，用于解析 txt 配置文件
from PIL import Image, ImageTk


class AutoSketchApp:
    def __init__(self, root):
        self.root = root
        self.root.title("杀戮尖塔2 自动素描机器人")
        # ★ 优化：调整初始尺寸，设定最小尺寸，并允许自由缩放
        self.root.geometry("520x700") 
        self.root.minsize(450, 400) # 设定最小宽度和高度，防止UI崩溃
        self.root.attributes("-topmost", True)

        self.is_running = False
        self.is_paused = False       
        self.stop_requested = False
        self.image_path = None
        self.contours = []
        self.image_size = (0, 0)
        self.config_file = "config.txt"  # ★ 新增：指定外部配置文件的名称

        self.setup_ui()
        self.load_config()               # ★ 新增：在UI构建完毕后，立刻加载外部配置覆盖默认值

        keyboard.add_hotkey('F9', self.on_hotkey_start)
        keyboard.add_hotkey('F8', self.on_hotkey_pause)  
        keyboard.add_hotkey('F10', self.on_hotkey_stop)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        style = ttk.Style()
        style.configure("TLabel", font=("Microsoft YaHei", 9))
        style.configure("TButton", font=("Microsoft YaHei", 10))

        # ★ 核心升级：创建全局响应式滚动视图 (Scrollable Frame)
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill="both", expand=True)

        self.main_canvas = tk.Canvas(self.main_frame, highlightthickness=0)
        self.main_canvas.pack(side="left", fill="both", expand=True)

        self.scrollbar = ttk.Scrollbar(self.main_frame, orient="vertical", command=self.main_canvas.yview)
        self.scrollbar.pack(side="right", fill="y")

        self.main_canvas.configure(yscrollcommand=self.scrollbar.set)

        # 真正承载所有 UI 元素的容器
        self.content_frame = ttk.Frame(self.main_canvas)
        self.canvas_window = self.main_canvas.create_window((0, 0), window=self.content_frame, anchor="nw")

        # 绑定事件：当内容发生变化时，更新滚动条范围
        self.content_frame.bind(
            "<Configure>",
            lambda e: self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))
        )
        # 绑定事件：当窗口宽度发生变化时，让内容框跟随自适应变宽
        self.main_canvas.bind(
            "<Configure>",
            lambda e: self.main_canvas.itemconfig(self.canvas_window, width=e.width)
        )
        
        # 绑定鼠标滚轮事件支持上下滚动
        self.root.bind_all("<MouseWheel>", lambda e: self.main_canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # -----------------------------------------------------------
        # ★ 将原有的 self.root 替换为 self.content_frame，挂载到滚动视图中
        # -----------------------------------------------------------

        # --- 第一部分：图片加载与预览 ---
        img_frame = ttk.LabelFrame(self.content_frame, text=" 图片设置 ")
        img_frame.pack(fill="x", padx=15, pady=5)

        ttk.Button(img_frame, text="📁 选择并上传图片", command=self.load_image).pack(pady=5)

        self.preview_canvas = tk.Canvas(img_frame, width=300, height=200, bg="black")
        self.preview_canvas.pack(pady=5)
        self.preview_label = ttk.Label(img_frame, text="等待上传图片...", foreground="gray")
        self.preview_label.pack()

        detail_frame = ttk.Frame(img_frame)
        detail_frame.pack(fill="x", padx=10, pady=5)
        
        # 1. 线条细节阈值
        ttk.Label(detail_frame, text="线条细节(阈值):").grid(row=0, column=0, sticky="w", pady=2)
        self.threshold_var = tk.IntVar(value=100)
        thresh_spin = ttk.Spinbox(detail_frame, from_=10, to=200, textvariable=self.threshold_var, width=5, command=self.update_preview)
        thresh_spin.grid(row=0, column=2, padx=(0, 5))
        thresh_spin.bind('<Return>', self.update_preview)
        thresh_scale = ttk.Scale(detail_frame, from_=10, to=200, variable=self.threshold_var, orient="horizontal")
        thresh_scale.grid(row=0, column=1, sticky="ew", padx=5)
        thresh_scale.bind("<ButtonRelease-1>", self.update_preview)

        # 2. 过滤短线防噪点
        ttk.Label(detail_frame, text="过滤短线(防噪点):").grid(row=1, column=0, sticky="w", pady=2)
        self.min_len_var = tk.IntVar(value=10) 
        minlen_spin = ttk.Spinbox(detail_frame, from_=0, to=100, textvariable=self.min_len_var, width=5, command=self.update_preview)
        minlen_spin.grid(row=1, column=2, padx=(0, 5))
        minlen_spin.bind('<Return>', self.update_preview)
        minlen_scale = ttk.Scale(detail_frame, from_=0, to=100, variable=self.min_len_var, orient="horizontal")
        minlen_scale.grid(row=1, column=1, sticky="ew", padx=5)
        minlen_scale.bind("<ButtonRelease-1>", self.update_preview)
        
        detail_frame.columnconfigure(1, weight=1)

        # --- 第二部分：绘图区域设置 (红框参数) ---
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

        # ★ 新增：框选屏幕区域的截取按钮
        ttk.Button(area_frame, text="✂️ 手动框选作画区域", command=self.start_area_selection).grid(row=2, column=0, columnspan=4, pady=(10, 5))

        # --- 第三部分：绘制参数 ---
        draw_frame = ttk.LabelFrame(self.content_frame, text=" 绘制参数 (防乱线设置) ")
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
        ttk.Checkbutton(draw_frame, text="暂停恢复时自动寻找并物理对齐地图", variable=self.auto_align_var).grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky="w")

        # ★ 新增：全局配置保存按钮
        ttk.Button(self.content_frame, text="💾 保存当前所有设置至配置文件", command=self.save_all_to_config).pack(pady=(15, 0))

        # --- 状态与控制 ---
        ttk.Label(self.content_frame, text="F9: 开始 | F8: 暂停/继续 | F10: 停止", foreground="red",
                  font=("Microsoft YaHei", 10, "bold")).pack(pady=10)
        self.status_label = ttk.Label(self.content_frame, text="当前状态: 请先上传图片", font=("Microsoft YaHei", 11, "bold"),
                                      foreground="blue")
        self.status_label.pack(pady=5)

    # ★ 新增核心功能：配置加载与解析
    def load_config(self):
        """加载或创建配置文件"""
        # 如果文件不存在，则自动生成带有详细中文注释的默认配置文件
        if not os.path.exists(self.config_file):
            self.create_default_config()

        config = configparser.ConfigParser()
        try:
            # 必须指定 utf-8 编码，防止中文注释乱码报错
            config.read(self.config_file, encoding='utf-8')
            
            # 读取并设置各个参数，如果文本里被误删找不到键值，则 fallback 回退到UI的默认值
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
            
        except Exception as e:
            print(f"配置文件读取有误，将使用默认参数: {e}")

    # ★ 新增核心功能：自动生成规范 txt 文件
    def create_default_config(self):
        """生成带有中文注释的默认 txt 配置文件"""
        default_content = """# ==========================================
# 杀戮尖塔2自动素描机器人 - 本地配置文件
# 格式说明：可以直接修改等号后面的数值。
# 修改完成后，重新打开软件即可生效！
# ==========================================

[线条设置]
# 线条细节(阈值)，建议范围 10~200。默认: 100
threshold = 100

# 过滤短线(防噪点)，去掉肉眼看不见的微小碎屑。默认: 10
min_len = 10

[绘制区域]
# 游戏红框避开的百分比 (0-50)
left_margin = 16
right_margin = 19
top_margin = 9
bottom_margin = 7

[绘制参数]
# 拖拽步长(像素)，控制线条平滑度。默认: 5
drag_step = 5

# 起落笔延迟(秒)，防止物理粘连飞线。极速推荐: 0.015~0.02
delay = 0.02

# 使用按键 (left 或 right)。默认: right
mouse_btn = right

# 暂停恢复时，是否自动寻找并物理对齐地图 (True 或 False)。默认: True
auto_align = True
"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                f.write(default_content)
        except Exception as e:
            print(f"创建配置文件失败: {e}")

    # ★ 修改：将原先的自动保存改为手动全局保存，并覆盖所有参数
    def save_all_to_config(self):
        if not os.path.exists(self.config_file):
            self.create_default_config()
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            with open(self.config_file, 'w', encoding='utf-8') as f:
                for line in lines:
                    if line.startswith('threshold ='): f.write(f"threshold = {self.threshold_var.get()}\n")
                    elif line.startswith('min_len ='): f.write(f"min_len = {self.min_len_var.get()}\n")
                    elif line.startswith('left_margin ='): f.write(f"left_margin = {self.left_margin.get()}\n")
                    elif line.startswith('right_margin ='): f.write(f"right_margin = {self.right_margin.get()}\n")
                    elif line.startswith('top_margin ='): f.write(f"top_margin = {self.top_margin.get()}\n")
                    elif line.startswith('bottom_margin ='): f.write(f"bottom_margin = {self.bottom_margin.get()}\n")
                    elif line.startswith('drag_step ='): f.write(f"drag_step = {self.drag_step_var.get()}\n")
                    elif line.startswith('delay ='): f.write(f"delay = {self.delay_var.get()}\n")
                    elif line.startswith('mouse_btn ='): f.write(f"mouse_btn = {self.btn_var.get()}\n")
                    elif line.startswith('auto_align ='): f.write(f"auto_align = {self.auto_align_var.get()}\n")
                    else: f.write(line)
            messagebox.showinfo("保存成功", "当前所有的参数设置已成功保存至 config.txt！\n下次启动将默认使用此配置。")
        except Exception as e:
            messagebox.showerror("保存失败", f"保存配置失败: {e}")

    # ★ 新增核心功能：半透明全屏框选截图器
    def start_area_selection(self):
        # 隐藏主窗口，避免遮挡玩家视线
        self.root.withdraw()
        time.sleep(0.2)  # 给系统一点时间隐藏窗口

        self.overlay = tk.Toplevel()
        self.overlay.attributes('-fullscreen', True)
        self.overlay.attributes('-alpha', 0.4) # 设置半透明暗角效果
        self.overlay.attributes('-topmost', True)
        self.overlay.config(bg='black', cursor="crosshair") # 准星鼠标

        self.overlay_canvas = tk.Canvas(self.overlay, bg="black", highlightthickness=0)
        self.overlay_canvas.pack(fill="both", expand=True)

        self.sel_rect = None
        self.start_x = 0
        self.start_y = 0

        # 绑定鼠标拖拽事件和退出事件
        self.overlay_canvas.bind("<ButtonPress-1>", self.on_selection_start)
        self.overlay_canvas.bind("<B1-Motion>", self.on_selection_drag)
        self.overlay_canvas.bind("<ButtonRelease-1>", self.on_selection_end)
        self.overlay.bind("<Escape>", self.cancel_selection)   # 按ESC取消
        self.overlay.bind("<Button-3>", self.cancel_selection) # 右键也能取消

    def cancel_selection(self, event=None):
        self.overlay.destroy()
        self.root.deiconify() # 恢复显示主窗口

    def on_selection_start(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.sel_rect:
            self.overlay_canvas.delete(self.sel_rect)
        self.sel_rect = self.overlay_canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y, outline="red", width=3)

    def on_selection_drag(self, event):
        self.overlay_canvas.coords(self.sel_rect, self.start_x, self.start_y, event.x, event.y)

    def on_selection_end(self, event):
        end_x, end_y = event.x, event.y
        screen_w = self.overlay.winfo_width()
        screen_h = self.overlay.winfo_height()

        self.overlay.destroy()
        self.root.deiconify() # 恢复显示主窗口

        x1, x2 = min(self.start_x, end_x), max(self.start_x, end_x)
        y1, y2 = min(self.start_y, end_y), max(self.start_y, end_y)

        # 限制框选范围不能太小（防止不小心点了一下误触）
        if x2 - x1 < 50 or y2 - y1 < 50:
            messagebox.showwarning("提示", "框选范围太小，已取消修改。")
            return

        # 根据绝对像素点，智能逆推四个方向的百分比
        left_pct = int((x1 / screen_w) * 100)
        right_pct = int(((screen_w - x2) / screen_w) * 100)
        top_pct = int((y1 / screen_h) * 100)
        bottom_pct = int(((screen_h - y2) / screen_h) * 100)

        # 安全限制在 0 - 50 之间，填入 UI
        self.left_margin.set(max(0, min(50, left_pct)))
        self.right_margin.set(max(0, min(50, right_pct)))
        self.top_margin.set(max(0, min(50, top_pct)))
        self.bottom_margin.set(max(0, min(50, bottom_pct)))

        # ★ 取消了自动保存，仅提示更新成功
        messagebox.showinfo("提示", "绘制区域已更新！\n（如需永久保留此设置，请点击主界面底部的“保存”按钮）")

    def load_image(self):
        file_path = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp")])
        if file_path:
            self.image_path = file_path
            self.update_preview()
            self.status_label.config(text="当前状态: 准备就绪", foreground="green")

    def update_preview(self, *args):
        if not self.image_path:
            return

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
            if cv2.arcLength(c, True) < min_len:
                continue
                
            epsilon = 0.001 * cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, epsilon, False)
            if len(approx) > 1:
                raw_contours.append(approx)

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
                        min_dist = dist_to_start
                        best_idx = i
                        reverse_best = False
                    if dist_to_end < min_dist:
                        min_dist = dist_to_end
                        best_idx = i
                        reverse_best = True

                best_contour = unvisited.pop(best_idx)
                if reverse_best:
                    best_contour = best_contour[::-1]

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

    def start_drawing(self):
        self.is_running = True
        self.is_paused = False
        self.stop_requested = False
        self.status_label.config(text="正在作画中! (F8暂停 | F10停止)", foreground="red")
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

            self.root.after(0, lambda: self.status_label.config(text="当前状态: 已暂停 (按F8继续)", foreground="purple"))
            
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
                    self.root.after(0, lambda: messagebox.showwarning("对齐失败", "滚动搜索未能找回原位置，将在当前位置继续强行绘制。"))
            
            self.root.after(0, lambda: self.status_label.config(text="正在作画中! (F8暂停 | F10停止)", foreground="red"))
            
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
    root = tk.Tk()
    app = AutoSketchApp(root)
    root.mainloop()