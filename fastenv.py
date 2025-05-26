import os
import sys
import time
import zipfile
import hashlib
import tkinter as tk
from tkinter import messagebox, filedialog, ttk
from threading import Thread
import requests
from urllib.parse import urlsplit
from pathlib import Path
import logging
import shutil
import subprocess
import json
from datetime import datetime
from queue import Queue

# 配置日志
log_file = f"installer_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),  # 指定文件编码为utf-8
        logging.StreamHandler()
    ]
)

# 需要下载的工具配置
TOOLS = {
    "Clangd": {
        "url": "https://github.com/clangd/clangd/releases/download/20.1.0/clangd-windows-20.1.0.zip",
        "bin_subdir": "bin",
        "is_single_exe": False,
        "description": "C/C++语言服务器，提供代码补全、错误检查等功能",
        "version": "20.1.0"
    },
    "ARM-GCC": {
        "url": "https://developer.arm.com/-/media/Files/downloads/gnu/14.2.rel1/binrel/arm-gnu-toolchain-14.2.rel1-mingw-w64-x86_64-arm-none-eabi.zip",
        "bin_subdir": "bin",
        "is_single_exe": False,
        "description": "ARM架构的GCC编译器工具链",
        "version": "14.2.rel1"
    },
    "CMake": {
        "url": "https://github.com/Kitware/CMake/releases/download/v4.0.1/cmake-4.0.1-windows-x86_64.zip",
        "bin_subdir": "bin",
        "is_single_exe": False,
        "description": "跨平台构建工具",
        "version": "4.0.1"
    },
    "Ninja": {
        "url": "https://github.com/ninja-build/ninja/releases/download/v1.12.1/ninja-win.zip",
        "bin_subdir": "",
        "is_single_exe": True,
        "description": "小型构建系统，专注于速度",
        "version": "1.12.1"
    },
    "OpenOCD": {
        "url": "https://github.com/xpack-dev-tools/openocd-xpack/releases/download/v0.12.0-6/xpack-openocd-0.12.0-6-win32-x64.zip",
        "bin_subdir": "bin",
        "is_single_exe": False,
        "description": "片上调试器，用于嵌入式设备编程和调试",
        "version": "0.12.0-6"
    }
}

# 安装步骤
INSTALL_STEPS = [
    {"id": "download", "text": "下载", "color": "#2196f3"},
    {"id": "extract", "text": "解压", "color": "#ff9800"},
    {"id": "config", "text": "配置", "color": "#4caf50"}
]


class ModernUI:
    """现代UI样式类"""
    COLORS = {
        "primary": "#4a6baf",  # 蓝色
        "primary_light": "#6b8fd4",
        "primary_dark": "#2a4b8f",
        "secondary": "#ffcdd2",  # 粉色
        "text": "#333333",
        "text_light": "#666666",
        "success": "#4caf50",
        "warning": "#ff9800",
        "error": "#f44336",
        "info": "#2196f3",
        "background": "#f8f9fa",  # 白色
        "card": "#ffffff",
        "border": "#e0e0e0"
    }

    @staticmethod
    def apply_theme(root):
        """应用现代UI主题到Tkinter"""
        style = ttk.Style()
        style.theme_use('clam')

        # 配置标准进度条样式
        style.configure(
            "TProgressbar",
            thickness=10,
            troughcolor=ModernUI.COLORS["secondary"],
            background=ModernUI.COLORS["primary"],
            borderwidth=0,
            relief="flat"
        )

        # 为每个步骤创建单独的进度条样式，确保包含Horizontal前缀
        for step in INSTALL_STEPS:
            style_name = f"{step['id']}.TProgressbar"
            style.configure(
                style_name,
                thickness=8,
                troughcolor=ModernUI.COLORS["secondary"],
                background=step["color"],
                borderwidth=0,
                relief="flat"
            )
            # 复制Horizontal.TProgressbar的布局
            style.layout(
                style_name,
                style.layout("Horizontal.TProgressbar")
            )

        # 配置按钮样式
        style.configure(
            "TButton",
            background=ModernUI.COLORS["primary"],
            foreground="white",
            borderwidth=0,
            focusthickness=3,
            focuscolor=ModernUI.COLORS["primary_light"],
            padding=(10, 5)
        )
        style.map(
            "TButton",
            background=[('active', ModernUI.COLORS["primary_light"]), ('disabled', ModernUI.COLORS["text_light"])]
        )

        return style


class InstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("开发工具安装助手")
        self.root.geometry("950x950")
        self.root.resizable(True, True)
        self.root.minsize(950, 950)

        self.style = ModernUI.apply_theme(self.root)

        self.save_dir = Path()
        self.progress_bars = {}
        self.step_progress_bars = {}
        self.status_labels = {}
        self.threads = {}
        self.existing_files = {}
        self.installation_completed = False
        self.ui_update_queue = Queue()

        self.main_frame = tk.Frame(self.root, bg=ModernUI.COLORS["background"])
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        self.setup_ui()
        self.root.after(100, self.process_ui_updates)

    def process_ui_updates(self):
        """处理UI更新队列"""
        while not self.ui_update_queue.empty():
            update_func = self.ui_update_queue.get()
            update_func()
        self.root.after(100, self.process_ui_updates)

    def setup_ui(self):
        # 设置全局字体为微软雅黑
        default_font = ("Microsoft YaHei", 9)
        self.root.option_add("*Font", default_font)

        header_frame = tk.Frame(self.main_frame, bg=ModernUI.COLORS["background"], pady=10)
        header_frame.pack(fill=tk.X)

        title_label = tk.Label(
            header_frame,
            text="嵌入式开发工具安装助手",
            font=("Microsoft YaHei", 16, "bold"),
            bg=ModernUI.COLORS["background"],
            fg=ModernUI.COLORS["primary"]
        )
        title_label.pack()

        subtitle_label = tk.Label(
            header_frame,
            text="本工具将下载并安装以下开发工具，请确保网络通畅",
            font=("Microsoft YaHei", 10),
            bg=ModernUI.COLORS["background"],
            fg=ModernUI.COLORS["text_light"]
        )
        subtitle_label.pack(pady=(5, 10))

        dir_frame = tk.Frame(self.main_frame, bg=ModernUI.COLORS["background"], pady=5)
        dir_frame.pack(fill=tk.X)

        self.dir_button = ttk.Button(
            dir_frame,
            text="选择安装目录",
            command=self.choose_directory,
            style="TButton"
        )
        self.dir_button.pack(side=tk.LEFT, padx=20)

        self.dir_label = tk.Label(
            dir_frame,
            text="请选择安装目录",
            font=default_font,
            fg=ModernUI.COLORS["text_light"],
            bg=ModernUI.COLORS["background"],
            padx=10
        )
        self.dir_label.pack(side=tk.LEFT, fill=tk.X)

        tools_container = tk.Frame(self.main_frame, bg=ModernUI.COLORS["background"], pady=10)
        tools_container.pack(fill=tk.BOTH, expand=True)

        tools_header = tk.Frame(tools_container, bg=ModernUI.COLORS["background"], pady=5)
        tools_header.pack(fill=tk.X)

        headers = ["工具", "版本", "状态", "进度"]
        widths = [100, 100, 100, 400]

        for i, header in enumerate(headers):
            tk.Label(
                tools_header,
                text=header,
                width=widths[i] // 10,
                font=("Microsoft YaHei", 10, "bold"),
                bg=ModernUI.COLORS["background"],
                fg=ModernUI.COLORS["text"]
            ).pack(side=tk.LEFT, padx=5)

        tools_canvas = tk.Canvas(tools_container, bg=ModernUI.COLORS["background"], highlightthickness=0)
        tools_scrollbar = ttk.Scrollbar(tools_container, orient="vertical", command=tools_canvas.yview)
        tools_scrollable_frame = tk.Frame(tools_canvas, bg=ModernUI.COLORS["background"])

        tools_scrollable_frame.bind(
            "<Configure>",
            lambda e: tools_canvas.configure(scrollregion=tools_canvas.bbox("all"))
        )

        tools_canvas.create_window((0, 0), window=tools_scrollable_frame, anchor="nw")
        tools_canvas.configure(yscrollcommand=tools_scrollbar.set)

        tools_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tools_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.progress_bars = {}
        self.step_progress_bars = {}
        self.status_labels = {}

        for tool_name, tool_config in TOOLS.items():
            tool_frame = tk.Frame(tools_scrollable_frame, bg=ModernUI.COLORS["card"], pady=10, padx=5, bd=1, relief=tk.SOLID)
            tool_frame.pack(fill=tk.X, pady=5, padx=10)

            tk.Label(
                tool_frame,
                text=tool_name,
                width=10,
                anchor='w',
                font=("Microsoft YaHei", 10, "bold"),
                bg=ModernUI.COLORS["card"],
                fg=ModernUI.COLORS["text"]
            ).pack(side=tk.LEFT, padx=5)

            tk.Label(
                tool_frame,
                text=tool_config.get("version", "未知"),
                width=10,
                anchor='w',
                font=default_font,
                bg=ModernUI.COLORS["card"],
                fg=ModernUI.COLORS["text_light"]
            ).pack(side=tk.LEFT, padx=5)

            status_label = tk.Label(
                tool_frame,
                text="等待开始",
                font=default_font,
                fg=ModernUI.COLORS["text_light"],
                bg=ModernUI.COLORS["card"],
                width=10
            )
            status_label.pack(side=tk.LEFT, padx=5)
            self.status_labels[tool_name] = status_label

            progress_container = tk.Frame(tool_frame, bg=ModernUI.COLORS["card"])
            progress_container.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

            progress_var = tk.DoubleVar()
            progress_bar = ttk.Progressbar(
                progress_container,
                variable=progress_var,
                length=350,
                mode='determinate',
                style="TProgressbar"
            )
            progress_bar.pack(fill=tk.X, pady=(0, 5))
            self.progress_bars[tool_name] = progress_var

            steps_frame = tk.Frame(progress_container, bg=ModernUI.COLORS["card"])
            steps_frame.pack(fill=tk.X)

            self.step_progress_bars[tool_name] = {}
            for step in INSTALL_STEPS:
                step_frame = tk.Frame(steps_frame, bg=ModernUI.COLORS["card"])
                step_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

                tk.Label(
                    step_frame,
                    text=step["text"],
                    font=("Microsoft YaHei", 8),
                    bg=ModernUI.COLORS["card"],
                    fg=ModernUI.COLORS["text_light"]
                ).pack(anchor='w')

                step_var = tk.DoubleVar()
                step_bar = ttk.Progressbar(
                    step_frame,
                    variable=step_var,
                    length=100,
                    mode='determinate',
                    style=f"{step['id']}.TProgressbar"
                )
                step_bar.pack(fill=tk.X)
                self.step_progress_bars[tool_name][step["id"]] = step_var

            tooltip_frame = tk.Frame(tools_scrollable_frame, bg=ModernUI.COLORS["background"], pady=2)
            tooltip_frame.pack(fill=tk.X, padx=10)

            tk.Label(
                tooltip_frame,
                text=f"描述: {tool_config.get('description', '无描述')}",
                anchor='w',
                font=("Microsoft YaHei", 8),
                bg=ModernUI.COLORS["background"],
                fg=ModernUI.COLORS["text_light"]
            ).pack(side=tk.LEFT, padx=20)

        button_frame = tk.Frame(self.main_frame, bg=ModernUI.COLORS["background"], pady=15)
        button_frame.pack(fill=tk.X)

        self.install_button = ttk.Button(
            button_frame,
            text="开始安装",
            command=self.start_installation,
            state=tk.DISABLED,
            style="TButton"
        )
        self.install_button.pack(side=tk.RIGHT, padx=20)

        self.cancel_button = ttk.Button(
            button_frame,
            text="取消",
            command=self.cancel_installation,
            state=tk.DISABLED,
            style="TButton"
        )
        self.cancel_button.pack(side=tk.RIGHT, padx=5)

        self.status_bar = tk.Label(
            self.main_frame,
            text="准备就绪",
            bd=1,
            relief=tk.SUNKEN,
            anchor=tk.W,
            font=default_font,
            bg=ModernUI.COLORS["secondary"],
            fg=ModernUI.COLORS["text_light"]
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def choose_directory(self):
        """选择安装目录并检查权限"""
        directory = filedialog.askdirectory(title="选择工具下载目录")
        if directory:
            self.save_dir = Path(directory)
            self.dir_label.config(text=f"安装目录: {directory}", fg=ModernUI.COLORS["text"])

            self.install_button.config(state=tk.NORMAL)

            self.scan_existing_files()

            self.status_bar.config(text=f"已选择目录: {directory}")

    def scan_existing_files(self):
        self.existing_files = {}

        for tool_name, tool_config in TOOLS.items():
            filename = Path(urlsplit(tool_config["url"]).path).name
            file_path = self.save_dir / filename

            if file_path.is_file():
                file_size = file_path.stat().st_size
                self.existing_files[tool_name] = {
                    "path": file_path,
                    "size": file_size
                }

                self.update_status(tool_name, "已有文件", ModernUI.COLORS["info"])
                self.ui_update_queue.put(lambda t=tool_name: self.step_progress_bars[t]["download"].set(100))

                logging.info(f"发现已有文件: {filename} ({self.format_size(file_size)})")

    def format_size(self, size_bytes):
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    def start_installation(self):
        if not self.save_dir:
            messagebox.showerror("错误", "请先选择安装目录")
            return

        self.installation_completed = False

        self.install_button.config(state=tk.DISABLED)
        self.dir_button.config(state=tk.DISABLED)

        self.cancel_button.config(state=tk.NORMAL)

        self.status_bar.config(text="正在安装工具...")

        for tool_name in TOOLS:
            self.progress_bars[tool_name].set(0)
            for step in INSTALL_STEPS:
                self.step_progress_bars[tool_name][step["id"]].set(0)

        self.threads = {}
        for tool_name in TOOLS:
            if tool_name not in self.existing_files:
                self.update_status(tool_name, "准备中...", ModernUI.COLORS["warning"])

            thread = Thread(
                target=self.install_tool,
                args=(tool_name, TOOLS[tool_name]),
                daemon=True
            )
            self.threads[tool_name] = thread
            thread.start()

    def cancel_installation(self):
        if messagebox.askyesno("确认", "确定要取消安装吗？"):
            self.installation_completed = True
            self.status_bar.config(text="安装已取消")

            self.dir_button.config(state=tk.NORMAL)
            self.install_button.config(state=tk.NORMAL)
            self.cancel_button.config(state=tk.DISABLED)

            for tool_name in TOOLS:
                if tool_name in self.threads and self.threads[tool_name].is_alive():
                    self.update_status(tool_name, "已取消", ModernUI.COLORS["error"])

    def install_tool(self, tool_name, tool_config):
        try:
            if self.installation_completed:
                return
            tool_dir = self.save_dir / Path(urlsplit(tool_config["url"]).path).stem
            url = tool_config["url"]
            bin_subdir = tool_config["bin_subdir"]
            is_single_exe = tool_config.get("is_single_exe", False)
            filename = Path(urlsplit(url).path).name
            save_path = self.save_dir / filename

            if tool_name in self.existing_files:
                self.update_status(tool_name, "验证文件...", ModernUI.COLORS["info"])
                existing_file = self.existing_files[tool_name]["path"]
                save_path = existing_file
            else:
                self.update_status(tool_name, "下载中...", ModernUI.COLORS["info"])
                self.download_file(url, save_path, tool_name)

            if self.installation_completed:
                return

            self.update_status(tool_name, "解压中...", ModernUI.COLORS["info"])
            extract_dir = self.extract_file(save_path, tool_dir, tool_name)

            if self.installation_completed:
                return

            self.update_status(tool_name, "处理目录结构...", ModernUI.COLORS["info"])
            actual_tool_dir = self.fix_directory_structure(extract_dir, bin_subdir, is_single_exe)

            if self.installation_completed:
                return

            self.update_status(tool_name, "配置环境变量...", ModernUI.COLORS["info"])
            self.add_to_system_path(actual_tool_dir, bin_subdir, is_single_exe, tool_name)

            self.update_status(tool_name, "完成", ModernUI.COLORS["success"])

            self.check_all_completed()

        except Exception as e:
            self.update_status(tool_name, "失败", ModernUI.COLORS["error"])
            logging.error(f"{tool_name} 安装失败: {str(e)}", exc_info=True)
            messagebox.showerror("错误", f"{tool_name} 安装失败: {str(e)}")

    def fix_directory_structure(self, base_dir, bin_subdir, is_single_exe):
        base_dir = Path(base_dir).resolve()
        if is_single_exe:
            return base_dir

        target_bin = base_dir / bin_subdir
        if target_bin.is_dir() and any(target_bin.iterdir()):
            return base_dir

        subdirs = [d for d in base_dir.iterdir() if d.is_dir()]
        if len(subdirs) != 1:
            return base_dir

        nested_dir = subdirs[0]
        nested_bin = nested_dir / bin_subdir
        if is_single_exe or (nested_bin.is_dir() and any(nested_bin.iterdir())):
            self.move_contents(nested_dir, base_dir)
            try:
                shutil.rmtree(nested_dir)
            except OSError as e:
                logging.warning(f"无法删除嵌套目录 {nested_dir}: {str(e)}")
        return base_dir

    def move_contents(self, src_dir, dst_dir):
        for item in src_dir.iterdir():
            dst_item = dst_dir / item.name
            if dst_item.exists():
                if dst_item.is_dir():
                    shutil.rmtree(dst_item)
                else:
                    dst_item.unlink()
            shutil.move(str(item), str(dst_dir))

    def download_file(self, url, save_path, tool_name, max_retries=3):
        for attempt in range(max_retries):
            try:
                response = requests.get(url, stream=True, timeout=30)
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))

                if total_size == 0:
                    raise Exception("无法获取文件大小")

                save_path.parent.mkdir(parents=True, exist_ok=True)

                downloaded = 0
                with open(save_path, 'wb') as file:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            if self.installation_completed:
                                file.close()
                                save_path.unlink()
                                return False

                            file.write(chunk)
                            downloaded += len(chunk)

                            download_progress = (downloaded / total_size) * 100
                            self.ui_update_queue.put(lambda p=download_progress: self.step_progress_bars[tool_name]["download"].set(p))

                            total_progress = (downloaded / total_size) * 33
                            self.ui_update_queue.put(lambda p=total_progress: self.progress_bars[tool_name].set(p))

                            percent = (downloaded / total_size) * 100
                            self.status_bar.config(text=f"下载 {tool_name}: {self.format_size(downloaded)}/{self.format_size(total_size)} ({percent:.1f}%)")

                return True

            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt < max_retries - 1:
                    logging.warning(f"下载 {tool_name} 失败，第 {attempt + 1} 次重试: {str(e)}")
                    time.sleep(2 ** attempt)
                    continue
                raise Exception(f"下载失败（多次尝试后）: {str(e)}")
            except requests.HTTPError as e:
                raise Exception(f"下载失败（HTTP错误）: {str(e)}")
            except Exception as e:
                if save_path.is_file():
                    save_path.unlink()
                raise Exception(f"下载失败: {str(e)}")

    def extract_file(self, save_path, tool_dir, tool_name):
        try:
            if tool_dir.is_dir():
                shutil.rmtree(tool_dir)

            tool_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(save_path, 'r') as zip_ref:
                total_files = len(zip_ref.infolist())
                extracted = 0

                for file in zip_ref.infolist():
                    if self.installation_completed:
                        return None
                    zip_ref.extract(file, tool_dir)
                    extracted += 1

                    extract_progress = (extracted / total_files) * 100
                    self.ui_update_queue.put(lambda p=extract_progress: self.step_progress_bars[tool_name]["extract"].set(p))

                    total_progress = 33 + (extracted / total_files) * 33
                    self.ui_update_queue.put(lambda p=total_progress: self.progress_bars[tool_name].set(p))

                    self.status_bar.config(text=f"解压 {tool_name}: {extracted}/{total_files} 文件")

            return tool_dir
        except Exception as e:
            if tool_dir.is_dir():
                shutil.rmtree(tool_dir)
            raise Exception(f"解压失败: {str(e)}")

    def add_to_system_path(self, tool_dir, bin_subdir, is_single_exe, tool_name):
        target_path = tool_dir if is_single_exe else tool_dir / bin_subdir
        target_path = str(target_path.resolve())

        try:
            cmd = ["powershell.exe", "-NoProfile", "-Command",
                   "[Environment]::SetEnvironmentVariable('PATH', " +
                   "[Environment]::GetEnvironmentVariable('PATH', 'User') + ';" +
                   f"{target_path}'" + ", 'User')"]

            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            result = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo)

            if result.returncode != 0:
                raise Exception(f"设置PATH失败: {result.stderr}")

            logging.info(f"成功添加环境变量: {target_path}")

            self.ui_update_queue.put(lambda: self.step_progress_bars[tool_name]["config"].set(100))
            self.ui_update_queue.put(lambda: self.progress_bars[tool_name].set(100))
            messagebox.showinfo("配置成功", f"{tool_name} 环境变量配置成功！部分环境变量需要重启后生效。")

        except Exception as e:
            raise Exception(f"环境变量设置失败: {str(e)}")

    def update_status(self, tool_name, status, color):
        self.ui_update_queue.put(
            lambda: self.status_labels[tool_name].config(text=status, fg=color)
        )

    def check_all_completed(self):
        all_completed = True
        for tool_name, thread in self.threads.items():
            if thread.is_alive():
                all_completed = False
                break

        if all_completed and not self.installation_completed:
            self.installation_completed = True
            messagebox.showinfo("安装完成", "所有工具安装完成！\n部分环境变量需要重启后生效。")

            self.dir_button.config(state=tk.NORMAL)
            self.install_button.config(state=tk.NORMAL)
            self.cancel_button.config(state=tk.DISABLED)

            self.status_bar.config(text="安装完成")


def check_dependencies():
    missing_deps = []

    try:
        import requests
    except ImportError:
        missing_deps.append("requests")

    if missing_deps:
        deps_str = ", ".join(missing_deps)
        messagebox.showerror("依赖缺失", f"缺少以下依赖库: {deps_str}，请执行: pip install {deps_str}")
        sys.exit(1)


def main():
    check_dependencies()

    root = tk.Tk()
    app = InstallerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()    