import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import pyautogui
import keyboard
import time
import cv2
import numpy as np
import math
from PIL import Image, ImageTk


class AutoSketchApp:
    def __init__(self, root):
        self.root = root
        self.root.title("杀戮尖塔2 自动素描机器人")
        self.root.geometry("500x780") 
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        self.is_running = False
        self.is_paused = False       
        self.stop_requested = False
        self.image_path = None
        self.contours = []
        self.image_size = (0, 0)

        self.setup_ui()

        keyboard.add_hotkey('F9', self.on_hotkey_start)
        keyboard.add_hotkey('F8', self.on_hotkey_pause)  
        keyboard.add_hotkey('F10', self.on_hotkey_stop)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        style = ttk.Style()
        style.configure("TLabel", font=("Microsoft YaHei", 9))
        style.configure("TButton", font=("Microsoft YaHei", 10))

        # --- 第一部分：图片加载与预览 ---
        img_frame = ttk.LabelFrame(self.root, text=" 图片设置 ")
        img_frame.pack(fill="x", padx=15, pady=5)

        ttk.Button(img_frame, text="📁 选择并上传图片", command=self.load_image).pack(pady=5)

        self.canvas = tk.Canvas(img_frame, width=300, height=200, bg="black")
        self.canvas.pack(pady=5)
        self.preview_label = ttk.Label(img_frame, text="等待上传图片...", foreground="gray")
        self.preview_label.pack()

        # 使用 grid 布局使其更整齐
        detail_frame = ttk.Frame(img_frame)
        detail_frame.pack(fill="x", padx=10, pady=5)
        
        # 1. 线条细节阈值
        ttk.Label(detail_frame, text="线条细节(阈值):").grid(row=0, column=0, sticky="w", pady=2)
        self.threshold_var = tk.IntVar(value=100)
        thresh_spin = ttk.Spinbox(detail_frame, from_=10, to=200, textvariable=self.threshold_var, width=5,
                                  command=self.update_preview)
        thresh_spin.grid(row=0, column=2, padx=(0, 5))
        thresh_spin.bind('<Return>', self.update_preview)
        thresh_scale = ttk.Scale(detail_frame, from_=10, to=200, variable=self.threshold_var, orient="horizontal")
        thresh_scale.grid(row=0, column=1, sticky="ew", padx=5)
        thresh_scale.bind("<ButtonRelease-1>", self.update_preview)

        # ★ 2. 过滤短线 (解决微小飞线和局部模糊的终极武器)
        ttk.Label(detail_frame, text="过滤短线(防噪点):").grid(row=1, column=0, sticky="w", pady=2)
        self.min_len_var = tk.IntVar(value=10) # 默认过滤长度小于10的灰尘
        minlen_spin = ttk.Spinbox(detail_frame, from_=0, to=100, textvariable=self.min_len_var, width=5, command=self.update_preview)
        minlen_spin.grid(row=1, column=2, padx=(0, 5))
        minlen_spin.bind('<Return>', self.update_preview)
        minlen_scale = ttk.Scale(detail_frame, from_=0, to=100, variable=self.min_len_var, orient="horizontal")
        minlen_scale.grid(row=1, column=1, sticky="ew", padx=5)
        minlen_scale.bind("<ButtonRelease-1>", self.update_preview)
        
        detail_frame.columnconfigure(1, weight=1)

        # --- 第二部分：绘图区域设置 (红框参数) ---
        area_frame = ttk.LabelFrame(self.root, text=" 绘制区域 (红框范围 %) ")
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

        # --- 第三部分：绘制参数 ---
        draw_frame = ttk.LabelFrame(self.root, text=" 绘制参数 (防乱线设置) ")
        draw_frame.pack(fill="x", padx=15, pady=5)

        ttk.Label(draw_frame, text="拖拽步长(像素):").grid(row=0, column=0, padx=10, pady=5, sticky="e")
        self.drag_step_var = tk.IntVar(value=5)  
        ttk.Spinbox(draw_frame, from_=1, to=50, textvariable=self.drag_step_var, width=8).grid(row=0, column=1)

        ttk.Label(draw_frame, text="起落笔延迟 (秒):").grid(row=1, column=0, padx=10, pady=5, sticky="e")
        self.delay_var = tk.DoubleVar(value=0.01) # 默认设为0.01
        ttk.Spinbox(draw_frame, from_=0.00, to=0.2, increment=0.01, textvariable=self.delay_var, width=8).grid(row=1, column=1)

        ttk.Label(draw_frame, text="使用按键:").grid(row=0, column=2, padx=10, pady=5, sticky="e")
        self.btn_var = tk.StringVar(value="right")
        ttk.Combobox(draw_frame, textvariable=self.btn_var, values=["left", "right"], width=5, state="readonly").grid(row=0, column=3)

        self.auto_align_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(draw_frame, text="暂停恢复时自动寻找并物理对齐地图", variable=self.auto_align_var).grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky="w")

        # --- 状态与控制 ---
        ttk.Label(self.root, text="F9: 开始 | F8: 暂停/继续 | F10: 停止", foreground="red",
                  font=("Microsoft YaHei", 10, "bold")).pack(pady=5)
        self.status_label = ttk.Label(self.root, text="当前状态: 请先上传图片", font=("Microsoft YaHei", 11, "bold"),
                                      foreground="blue")
        self.status_label.pack(pady=5)

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
            # ★ 修复1：丢弃肉眼看不见的噪点碎屑，防止疯狂原地跳跃导致飞线
            if cv2.arcLength(c, True) < min_len:
                continue
                
            # ★ 修复2：彻底抛弃动态比例压缩！强制以 1.0 像素的最高精度还原曲线。
            # 这解决了嘴部被画成僵硬多边形、甚至多出一个圈的“低模Bug”。
            approx = cv2.approxPolyDP(c, 1.0, False)
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

        self.canvas.delete("all")
        self.canvas.create_image(150, 100, anchor="center", image=self.tk_img)
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
        
        # ★ 强制底层保底延迟机制：
        # 无论界面设置多低，底层都会保障至少 0.015 秒（约1帧）的延迟。
        # 这是为了 100% 确保游戏引擎能抓取到鼠标已经抬起，防止物理粘连飞线。
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

            # --- 1. 暂停前：截取中心区域锚点 ---
            if self.auto_align_var.get():
                self.root.after(0, lambda: self.status_label.config(text="正在保存地图锚点快照...", foreground="purple"))
                # ★ 修复3：扩大快照取样面积至 50%，增加特征点，防止认错坐标。
                aw, ah = int(box_w * 0.50), int(box_h * 0.50)
                ax, ay = int(box_x + (box_w - aw) / 2), int(box_y + (box_h - ah) / 2)
                anchor_img = pyautogui.screenshot(region=(ax, ay, aw, ah))
                anchor_cv = cv2.cvtColor(np.array(anchor_img), cv2.COLOR_RGB2BGR)
                old_rel_x = ax - box_x
                old_rel_y = ay - box_y

            self.root.after(0, lambda: self.status_label.config(text="当前状态: 已暂停 (按F8继续)", foreground="purple"))
            
            # --- 2. 阻塞等待 ---
            while self.is_paused and not self.stop_requested:
                time.sleep(0.1)
                
            if self.stop_requested:
                return False, 0, 0

            # --- 3. 恢复时：物理精准拖拽纠偏 ---
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
                    
                    # ★ 修复4：将匹配阈值从 0.65 史诗级拉高到 0.80！
                    # 宁愿找不到，也绝对不能找错位置画重影。
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
            
            pyautogui.moveTo(new_target_x, new_target_y)
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
                        pyautogui.moveTo(screen_x, screen_y)
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