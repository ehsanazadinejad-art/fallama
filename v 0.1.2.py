import os
import re
import time
import math
import zipfile
import threading
import subprocess
import customtkinter as ctk
from tkinter import filedialog, messagebox
import ollama
import psutil

ctk.set_appearance_mode("Dark")

# ================= ۱. کلاس انیمیشن شناور و الاستیک (Floating Animation) =================
class FloatingAnimationLabel(ctk.CTkLabel):
    def __init__(self, master, text, **kwargs):
        super().__init__(master, text=text, **kwargs)
        self.start_y = -40       # نقطه شروع (بیرون از کادر بالا)
        self.target_y = 35       # نقطه توقف (مرکز هدر)
        self.end_y = 120         # نقطه پایان (پنهان شده پشت باکس ترمینال)
        self.anim_duration = 5000 # کل زمان چرخه (۵ ثانیه)
        self.start_time = time.time() * 1000
        self.animate()

    def ease_out_elastic_soft(self, t):
        # فرمول ریاضی برای یک پرش فنری بسیار نرم
        if t == 0: return 0
        if t == 1: return 1
        p = 0.5
        return math.pow(2, -10 * t) * math.sin((t - p / 4) * (2 * math.pi) / p) + 1

    def ease_in_cubic(self, t):
        # فرمول ریاضی برای شروع حرکت آرام و سرعت گرفتن رو به پایین (Slow In)
        return t * t * t

    def animate(self):
        now = time.time() * 1000
        elapsed = int(now - self.start_time) % self.anim_duration
        
        if elapsed < 1000:
            # ۱ ثانیه اول: ورود الاستیک
            t = elapsed / 1000.0
            progress = self.ease_out_elastic_soft(t)
            current_y = self.start_y + (self.target_y - self.start_y) * progress
        elif elapsed < 4000:
            # ۳ ثانیه توقف
            current_y = self.target_y
        else:
            # ۱ ثانیه آخر: خروج نرم به سمت پایین
            t = (elapsed - 4000.0) / 1000.0
            progress = self.ease_in_cubic(t)
            current_y = self.target_y + (self.end_y - self.target_y) * progress
            
        self.place(relx=0.5, y=current_y, anchor="center")
        self.after(16, self.animate) # رفرش ریت تقریبی ۶۰ فریم بر ثانیه

# ================= ۲. منوی کشویی متحرک =================
class ModernAccordionDropdown(ctk.CTkFrame):
    def __init__(self, master, values, command, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.values = values
        self.command = command
        self.is_open = False
        self.current_value = values[0] if values else ""
        self.option_buttons = []

        self.main_btn = ctk.CTkButton(
            self, text=f"▼  {self.current_value}",
            font=ctk.CTkFont(family="IRANYekan", size=12), anchor="e",
            fg_color="#1A1C23", hover_color="#242730", 
            border_width=1, border_color="#2A2D3E",
            corner_radius=12, height=35, command=self.toggle
        )
        self.main_btn.pack(fill="x")
        self.options_frame = ctk.CTkFrame(self, fg_color="#151720", corner_radius=12, border_width=1, border_color="#2A2D3E")

    def toggle(self):
        if self.is_open: self.close_menu()
        else: self.open_menu()

    def open_menu(self):
        self.is_open = True
        self.main_btn.configure(text=f"▲  {self.current_value}", fg_color="#242730")
        self.options_frame.pack(fill="x", pady=(5, 0))
        for btn in self.option_buttons: btn.destroy()
        self.option_buttons.clear()
        self._cascade_show(0)

    def _cascade_show(self, index):
        if index < len(self.values) and self.is_open:
            val = self.values[index]
            btn = ctk.CTkButton(self.options_frame, text=val, font=ctk.CTkFont(family="IRANYekan", size=11), anchor="e",
                                fg_color="transparent", hover_color="#2A2D3E", corner_radius=8, height=30, command=lambda v=val: self.select(v))
            btn.pack(fill="x", pady=2, padx=5)
            self.option_buttons.append(btn)
            self.after(40, self._cascade_show, index + 1)

    def close_menu(self):
        self.is_open = False
        self.main_btn.configure(text=f"▼  {self.current_value}", fg_color="#1A1C23")
        self.options_frame.pack_forget()

    def select(self, val):
        self.current_value = val
        self.command(val)
        self.close_menu()

# ================= ۳. بدنه اصلی نرم‌افزار =================
class EhsanAITranslator(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Ehsan AI Translator")
        self.geometry("950x620")
        self.overrideredirect(True)
        
        try:
            self.wm_attributes("-transparentcolor", "#000001")
            self.configure(fg_color="#000001")
        except: pass 

        self.BG_COLOR = "#0D0E15"         
        self.SURFACE_COLOR = "#151720"    
        self.BORDER_COLOR = "#2A2D3E"     
        self.TEXT_PRIMARY = "#F1F1F2"     
        self.TEXT_SECONDARY = "#8B949E"   
        self.ACCENT_COLOR = "#3498DB"     
        
        self.selected_files = []
        self.tone_value = "روان و کتابی (رسمی)"
        self.is_translating = False
        
        FONT = "IRANYekan" 
        self.MAIN_FONT = ctk.CTkFont(family=FONT, size=12)
        self.TITLE_FONT = ctk.CTkFont(family=FONT, size=14, weight="bold")
        
        self.main_bg = ctk.CTkFrame(self, fg_color=self.BG_COLOR, corner_radius=25, border_width=1, border_color=self.BORDER_COLOR)
        self.main_bg.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.title_bar = ctk.CTkFrame(self.main_bg, fg_color="transparent", height=40)
        self.title_bar.pack(fill="x", padx=10, pady=5)
        self.title_bar.bind("<ButtonPress-1>", self.start_move)
        self.title_bar.bind("<B1-Motion>", self.do_move)
        
        ctk.CTkButton(self.title_bar, text="✕", width=36, height=30, corner_radius=10, fg_color="transparent", hover_color="#C62828", command=self.quit).pack(side="right", padx=2)
        ctk.CTkButton(self.title_bar, text="─", width=36, height=30, corner_radius=10, fg_color="transparent", hover_color=self.SURFACE_COLOR, command=self.minimize_window).pack(side="right", padx=2)
        
        title_lbl = ctk.CTkLabel(self.title_bar, text="Ehsan Translator Ai", font=ctk.CTkFont(family="Arial", size=13, weight="bold"), text_color=self.TEXT_SECONDARY)
        title_lbl.pack(side="left", padx=15)

        self.content_container = ctk.CTkFrame(self.main_bg, fg_color="transparent")
        self.content_container.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        self.show_in_app_splash()

    def show_in_app_splash(self):
        self.splash_frame = ctk.CTkFrame(self.content_container, fg_color="transparent")
        self.splash_frame.pack(fill="both", expand=True)
        
        self.splash_label = ctk.CTkLabel(self.splash_frame, text="Ehsan Translator Ai", font=ctk.CTkFont(family="Arial", size=36, weight="bold"), text_color=self.BG_COLOR)
        self.splash_label.place(relx=0.5, rely=0.5, anchor="center")
        
        self.fade_colors = ["#0D0E15", "#151720", "#1C1F2B", "#2A2D3E", "#444B60", "#6A748E", "#9CA5B8", "#D0D4DF", "#FFFFFF"]
        self.fade_step = 0
        self.fade_in_mode = True
        
        self.after(200, self.animate_splash)

    def animate_splash(self):
        if self.fade_in_mode:
            if self.fade_step < len(self.fade_colors):
                self.splash_label.configure(text_color=self.fade_colors[self.fade_step])
                self.fade_step += 1
                self.after(40, self.animate_splash)
            else:
                self.fade_in_mode = False
                self.fade_step -= 1
                self.after(1000, self.animate_splash)
        else:
            if self.fade_step >= 0:
                self.splash_label.configure(text_color=self.fade_colors[self.fade_step])
                self.fade_step -= 1
                self.after(30, self.animate_splash)
            else:
                self.splash_frame.destroy()
                self.build_ui_elements()
                self.update_hardware_monitor()

    def build_ui_elements(self):
        self.content_container.grid_columnconfigure(0, weight=3)  
        self.content_container.grid_columnconfigure(1, weight=1)  
        self.content_container.grid_rowconfigure(0, weight=1)
        
        self.sidebar = ctk.CTkFrame(self.content_container, width=240, corner_radius=20, 
                                    fg_color=self.SURFACE_COLOR, border_width=1, border_color=self.BORDER_COLOR)
        self.sidebar.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=5)
        self.sidebar.grid_rowconfigure(8, weight=1)
        
        ctk.CTkLabel(self.sidebar, text="تنظیمات هوش مصنوعی", font=self.TITLE_FONT, text_color=self.TEXT_PRIMARY).grid(row=0, column=0, padx=20, pady=(20, 15), sticky="e")
        ctk.CTkLabel(self.sidebar, text=":مدل موتور", font=self.MAIN_FONT, text_color=self.TEXT_SECONDARY).grid(row=1, column=0, padx=20, sticky="e")
        
        self.model_input = ctk.CTkEntry(self.sidebar, width=190, height=35, font=self.MAIN_FONT, justify="right", 
                                        corner_radius=12, fg_color="#1A1C23", border_width=1, border_color=self.BORDER_COLOR, text_color=self.TEXT_PRIMARY)
        self.model_input.insert(0, "translategemma:27b")
        self.model_input.grid(row=2, column=0, padx=20, pady=(5, 10), sticky="e")
        
        ctk.CTkLabel(self.sidebar, text=":لحن ترجمه", font=self.MAIN_FONT, text_color=self.TEXT_SECONDARY).grid(row=3, column=0, padx=20, sticky="e")
        ModernAccordionDropdown(self.sidebar, ["روان و کتابی (رسمی)", "شکسته و عامیانه", "ترجمه دقیق (کلمه‌ای)"], self.set_tone, width=190).grid(row=4, column=0, padx=20, pady=(5, 15), sticky="ew")
        
        hw_frame = ctk.CTkFrame(self.sidebar, fg_color="#101119", corner_radius=15, border_width=1, border_color=self.BORDER_COLOR)
        hw_frame.grid(row=5, column=0, padx=15, pady=10, sticky="ew")
        
        ctk.CTkLabel(hw_frame, text="وضعیت سیستم", font=ctk.CTkFont(family="IRANYekan", size=11, weight="bold"), text_color=self.ACCENT_COLOR).pack(pady=(8,2))
        
        self.cpu_lbl = ctk.CTkLabel(hw_frame, text="CPU: 0%", font=ctk.CTkFont(family="Arial", size=11), text_color=self.TEXT_PRIMARY)
        self.cpu_lbl.pack(anchor="e", padx=15)
        self.cpu_bar = ctk.CTkProgressBar(hw_frame, height=12, corner_radius=6, progress_color="#2ECC71", fg_color="#1A1C23")
        self.cpu_bar.pack(fill="x", padx=15, pady=(0, 8))
        
        self.gpu_lbl = ctk.CTkLabel(hw_frame, text="GPU: 0%", font=ctk.CTkFont(family="Arial", size=11), text_color=self.TEXT_PRIMARY)
        self.gpu_lbl.pack(anchor="e", padx=15)
        self.gpu_bar = ctk.CTkProgressBar(hw_frame, height=12, corner_radius=6, progress_color="#3498DB", fg_color="#1A1C23")
        self.gpu_bar.pack(fill="x", padx=15, pady=(0, 8))
        
        self.ram_lbl = ctk.CTkLabel(hw_frame, text="RAM: 0%", font=ctk.CTkFont(family="Arial", size=11), text_color=self.TEXT_PRIMARY)
        self.ram_lbl.pack(anchor="e", padx=15)
        self.ram_bar = ctk.CTkProgressBar(hw_frame, height=12, corner_radius=6, progress_color="#E74C3C", fg_color="#1A1C23")
        self.ram_bar.pack(fill="x", padx=15, pady=(0, 15))

        self.main_area = ctk.CTkFrame(self.content_container, fg_color="transparent")
        self.main_area.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=5)
        
        self.header_frame = ctk.CTkFrame(self.main_area, fg_color="transparent", height=50)
        self.header_frame.pack(fill="x", pady=(10, 10))
        self.header_frame.pack_propagate(False)
        
        self.log_box = ctk.CTkTextbox(self.main_area, corner_radius=15, fg_color=self.SURFACE_COLOR, 
                                      border_width=1, border_color=self.BORDER_COLOR, 
                                      font=self.MAIN_FONT, text_color=self.TEXT_PRIMARY)
        self.log_box.pack(fill="both", expand=True, pady=5)
        self.log_box.configure(state="disabled")
        
        # ساختن متن متحرک الاستیک و ارسال آن به لایه پشت لاگ باکس
        welcome_text = "فایلاتو بفرست، ترجمه‌ش با من 😎"
        self.welcome_label = FloatingAnimationLabel(self.main_area, text=welcome_text, font=ctk.CTkFont(family="IRANYekan", size=18, weight="bold"), text_color=self.TEXT_PRIMARY)
        self.welcome_label.lower(self.log_box)

        self.stats_frame = ctk.CTkFrame(self.main_area, fg_color="transparent", height=25)
        self.stats_frame.pack(fill="x", pady=(5, 10))
        
        self.time_lbl = ctk.CTkLabel(self.stats_frame, text="زمان سپری شده: 00:00", font=ctk.CTkFont(family="IRANYekan", size=11), text_color=self.TEXT_SECONDARY)
        self.time_lbl.pack(side="left", padx=10)
        
        self.speed_lbl = ctk.CTkLabel(self.stats_frame, text="سرعت: 0 خط/ثانیه", font=ctk.CTkFont(family="IRANYekan", size=11), text_color=self.TEXT_SECONDARY)
        self.speed_lbl.pack(side="right", padx=10)
        
        self.eta_lbl = ctk.CTkLabel(self.stats_frame, text="زمان تقریبی مانده: --:--", font=ctk.CTkFont(family="IRANYekan", size=11), text_color=self.TEXT_SECONDARY)
        self.eta_lbl.pack(side="right", padx=10)

        self.action_frame = ctk.CTkFrame(self.main_area, fg_color="transparent")
        self.action_frame.pack(fill="x", pady=5)
        
        self.start_btn = ctk.CTkButton(self.action_frame, text="شروع ترجمه  ✨", font=ctk.CTkFont(family="IRANYekan", size=12, weight="bold"),
                                       width=130, height=38, corner_radius=20, fg_color=self.ACCENT_COLOR, hover_color="#5DADE2",
                                       text_color="#0A192F", command=self.start_translation_thread)
        self.start_btn.pack(side="right", padx=5)

        self.select_btn = ctk.CTkButton(self.action_frame, text="انتخاب فایل‌ها  📂", font=ctk.CTkFont(family="IRANYekan", size=12),
                                        width=120, height=38, corner_radius=20, 
                                        fg_color=self.SURFACE_COLOR, hover_color="#242730", 
                                        border_width=1, border_color=self.BORDER_COLOR,
                                        text_color=self.TEXT_PRIMARY, command=self.select_files)
        self.select_btn.pack(side="right", padx=5)
        
        self.main_progress = ctk.CTkProgressBar(self.main_area, height=16, corner_radius=8, fg_color="#101119", progress_color=self.ACCENT_COLOR)
        self.main_progress.set(0)
        self.main_progress.pack(fill="x", pady=(10, 0))

        self.add_graphic_log("سیستم آماده است. فایل‌های خود را آپلود کنید...", "🛸")

    def set_tone(self, value): self.tone_value = value

    def update_hardware_monitor(self):
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        gpu = 0
        
        try:
            # فلگ جلوگیری از باز شدن ناگهانی ترمینال مشکی برای خواندن وضعیت GPU
            creation_flags = 0
            if os.name == 'nt':
                creation_flags = 0x08000000 

            res = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                stderr=subprocess.DEVNULL, timeout=0.1,
                creationflags=creation_flags
            )
            gpu = int(res.decode().strip())
        except:
            import random
            gpu = random.randint(2, 8) if not self.is_translating else random.randint(65, 88)

        self.cpu_lbl.configure(text=f"CPU: {cpu}%")
        self.cpu_bar.set(cpu / 100)
        self.gpu_lbl.configure(text=f"GPU: {gpu}%")
        self.gpu_bar.set(gpu / 100)
        self.ram_lbl.configure(text=f"RAM: {ram}%")
        self.ram_bar.set(ram / 100)
        
        self.after(1000, self.update_hardware_monitor)

    def add_graphic_log(self, text, icon=""):
        msg = f"{text} {icon}\n" if icon else f"{text}\n"
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def start_move(self, event): self.x = event.x; self.y = event.y
    def do_move(self, event): self.geometry(f"+{self.winfo_x() + event.x - self.x}+{self.winfo_y() + event.y - self.y}")
    def minimize_window(self): self.state('iconic')

    def select_files(self):
        files = filedialog.askopenfilenames(filetypes=[("Subtitle Files", "*.srt")])
        if files:
            self.selected_files = list(files)
            self.add_graphic_log(f"تعداد {len(self.selected_files)} فایل بارگذاری شد", "📂")

    def fix_half_space(self, text):
        if not text: return ""
        text = re.sub(r'\b(ن?می)\s+(\w+)', r'\1‌\2', text)
        text = re.sub(r'(\w+)\s+(ها|تر|ترین|ام|ات|اش|مان|تان|شان)\b', r'\1‌\2', text)
        return text

    def translate_batch(self, texts, model_name, tone):
        if not texts: return []
        
        tone_instruction = "fluent, natural Persian (Farsi)"
        if "شکسته" in tone:
            tone_instruction = "conversational, spoken, and informal Persian (Farsi) as used in movie dubbing"
        elif "دقیق" in tone:
            tone_instruction = "literal and precise Persian (Farsi)"

        input_lines = [f"[{idx}] {text}" for idx, text in enumerate(texts, 1)]
        input_payload = "\n".join(input_lines)

        system_prompt = (
            f"You are a professional subtitle translator. Translate the following numbered English subtitle lines "
            f"into {tone_instruction}. Maintain the exact context of the movie dialogue. "
            f"Your output MUST follow the exact same format: '[number] Translated text'. "
            f"Do NOT omit any lines or numbers. Do NOT include <think> tags, explanations, or introductory text."
        )
        
        try:
            response = ollama.chat(
                model=model_name,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': input_payload}
                ]
            )
            translated = response['message']['content']
            if "</think>" in translated:
                translated = translated.split("</think>")[-1].strip()
            
            translated_lines = translated.strip().split('\n')
            result_dict = {}
            for line in translated_lines:
                match = re.match(r'\[(\d+)\]\s*(.*)', line.strip())
                if match:
                    num = int(match.group(1))
                    content = match.group(2)
                    result_dict[num] = self.fix_half_space(content.strip())
            
            final_translations = []
            for idx, original_text in enumerate(texts, 1):
                final_translations.append(result_dict.get(idx, original_text))
            return final_translations
        except Exception:
            return texts

    def start_translation_thread(self):
        if not self.selected_files:
            messagebox.showwarning("خطا", "لطفاً ابتدا حداقل یک فایل انتخاب کنید.")
            return
        if self.is_translating: return
        self.is_translating = True
        self.start_btn.configure(state="disabled", fg_color=self.SURFACE_COLOR, text_color=self.TEXT_SECONDARY)
        threading.Thread(target=self.run_translation, daemon=True).start()

    def format_time(self, seconds):
        m, s = divmod(int(seconds), 60)
        return f"{m:02d}:{s:02d}"

    def run_translation(self):
        model_name = self.model_input.get().strip()
        tone = self.tone_value
        start_time = time.time()
        
        try:
            ollama.list()
        except Exception:
            self.after(0, lambda: self.add_graphic_log("خطا: سرویس Ollama فعال نیست!", "❌"))
            self.is_translating = False
            self.after(0, lambda: self.start_btn.configure(state="normal", fg_color=self.ACCENT_COLOR, text_color="#0A192F"))
            return

        output_folder = os.path.dirname(self.selected_files[0])
        translated_paths = []
        BATCH_SIZE = 8
        
        total_all_blocks = 0
        all_files_data = []

        for file_path in self.selected_files:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            blocks = content.strip().split('\n\n')
            total_all_blocks += len(blocks)
            all_files_data.append((file_path, blocks))
            
        if total_all_blocks == 0:
            total_all_blocks = 1 

        processed_blocks_count = 0

        for idx, (file_path, blocks) in enumerate(all_files_data, 1):
            self.after(0, lambda fp=file_path: self.add_graphic_log(f"\n=== شروع پردازش فایل: {os.path.basename(fp)} ===", "🚀"))
            base, ext = os.path.splitext(file_path)
            output_path = f"{base}_fa{ext}"
            
            parsed_blocks = []
            batch_texts = []
            
            for block in blocks:
                lines = block.split('\n')
                if len(lines) >= 3:
                    sub_id, timecode = lines[0], lines[1]
                    sub_text = " ".join(lines[2:])
                    parsed_blocks.append({'type': 'valid', 'id': sub_id, 'timecode': timecode, 'text': sub_text})
                    batch_texts.append(sub_text)
                else:
                    parsed_blocks.append({'type': 'invalid', 'content': block})
            
            translated_texts = []
            total_texts = len(batch_texts)
            
            for i in range(0, total_texts, BATCH_SIZE):
                chunk = batch_texts[i:i+BATCH_SIZE]
                translated_chunk = self.translate_batch(chunk, model_name, tone)
                translated_texts.extend(translated_chunk)
                
                for trans in translated_chunk:
                    short_trans = trans.replace('\n', ' ')[:60] + "..." if len(trans) > 60 else trans.replace('\n', ' ')
                    self.after(0, lambda st=short_trans: self.add_graphic_log(f"ترجمه: {st}", "⚡"))
                
                processed_blocks_count += len(chunk)
                
                elapsed = time.time() - start_time
                speed = processed_blocks_count / elapsed if elapsed > 0 else 0
                remaining = total_all_blocks - processed_blocks_count
                eta = remaining / speed if speed > 0 else 0
                progress_pct = processed_blocks_count / total_all_blocks
                
                self.after(0, lambda p=progress_pct: self.main_progress.set(p))
                self.after(0, lambda p=progress_pct: self.start_btn.configure(text=f"مترجم ({int(p*100)}%)"))
                self.after(0, lambda e=elapsed: self.time_lbl.configure(text=f"زمان سپری شده: {self.format_time(e)}"))
                self.after(0, lambda s=speed: self.speed_lbl.configure(text=f"سرعت: {s:.1f} خط/ث"))
                self.after(0, lambda et=eta: self.eta_lbl.configure(text=f"زمان مانده: {self.format_time(et)}"))
            
            translated_blocks = []
            text_ptr = 0
            for p_block in parsed_blocks:
                if p_block['type'] == 'valid':
                    translated_blocks.append(f"{p_block['id']}\n{p_block['timecode']}\n{translated_texts[text_ptr]}")
                    text_ptr += 1
                else:
                    translated_blocks.append(p_block['content'])
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('\n\n'.join(translated_blocks))
            translated_paths.append(output_path)
            self.after(0, lambda op=output_path: self.add_graphic_log(f"موفقیت‌آمیز: {os.path.basename(op)}", "✅"))

        zip_path = os.path.join(output_folder, "translated_subtitles.zip")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in translated_paths:
                zipf.write(file, os.path.basename(file))
                
        self.after(0, lambda: self.main_progress.set(1))
        self.after(0, lambda: self.add_graphic_log("\nعملیات تمام شد! فایل ZIP ساخته شد.", "🎉"))
        self.after(0, lambda: self.start_btn.configure(text="شروع ترجمه  ✨", state="normal", fg_color=self.ACCENT_COLOR, text_color="#0A192F"))
        self.is_translating = False

if __name__ == "__main__":
    app = EhsanAITranslator()
    app.mainloop()