import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import requests
import sqlite3
import threading
import time
import datetime
import os
import csv
import json
import queue

try:
    import matplotlib
    matplotlib.use('TkAgg')
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    import matplotlib.dates as mdates
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

try:
    from PIL import Image, ImageDraw, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


DB_PATH = "monitor.db"
SITES_FILE = "sites.json"
DEFAULT_INTERVAL = 60
REQUEST_TIMEOUT = 10

THEMES = {
    'light': {
        'bg': '#f5f5f5', 'fg': '#202020', 'field': '#ffffff',
        'select': '#4a90d9', 'select_fg': 'white',
        'header': '#3498db', 'button': '#e0e0e0', 'button_fg': '#202020',
        'accent': '#3498db', 'ok': '#27ae60', 'error': '#e74c3c',
        'warn': '#f39c12', 'chart_bg': '#ffffff', 'chart_fg': '#202020',
        'chart_grid': '#cccccc',
    },
    'dark': {
        'bg': '#2b2b2b', 'fg': '#e0e0e0', 'field': '#3c3f41',
        'select': '#4a90d9', 'select_fg': 'white',
        'header': '#1f6feb', 'button': '#3c3f41', 'button_fg': '#e0e0e0',
        'accent': '#4a90d9', 'ok': '#2ecc71', 'error': '#e74c3c',
        'warn': '#f39c12', 'chart_bg': '#2b2b2b', 'chart_fg': '#e0e0e0',
        'chart_grid': '#555555',
    }
}


class SiteMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Мониторинг доступности сайтов")
        self.root.geometry("1150x760")

        self.sites = []
        self.running = False
        self.interval = DEFAULT_INTERVAL
        self.theme_name = 'light'
        self.result_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.db_lock = threading.Lock()

        self.init_db()
        self.load_sites()
        self.setup_ui()
        self.apply_theme()
        self.refresh_site_tree()
        self.setup_icon()

        self.root.after(200, self.poll_results)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- Иконка ----------
    def setup_icon(self):
        if not HAS_PIL:
            return
        try:
            img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.ellipse((2, 2, 62, 62), fill=(52, 152, 219, 255))
            d.ellipse((18, 18, 46, 46), fill=(46, 204, 113, 255))
            for (a, b, c, e) in [(32, 2, 32, 18), (32, 46, 32, 62),
                                 (2, 32, 18, 32), (46, 32, 62, 32)]:
                d.line((a, b, c, e), fill=(255, 255, 255, 255), width=4)
            self.icon_photo = ImageTk.PhotoImage(img)
            self.root.iconphoto(True, self.icon_photo)
            try:
                img.save('icon.ico')
            except Exception:
                pass
        except Exception:
            pass

    # ---------- БД ----------
    def init_db(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                name TEXT,
                url TEXT NOT NULL,
                status TEXT,
                code INTEGER,
                time_ms REAL,
                error TEXT
            )
        """)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_url ON history(url)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON history(timestamp)")
        self.conn.commit()

    def load_sites(self):
        if os.path.exists(SITES_FILE):
            try:
                with open(SITES_FILE, 'r', encoding='utf-8') as f:
                    self.sites = json.load(f)
                return
            except Exception:
                pass
        self.sites = [
            {'name': 'Google', 'url': 'https://www.google.com'},
            {'name': 'GitHub', 'url': 'https://github.com'},
            {'name': 'Python.org', 'url': 'https://www.python.org'},
        ]
        self.save_sites()

    def save_sites(self):
        try:
            with open(SITES_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.sites, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------- Интерфейс ----------
    def setup_ui(self):
        toolbar = ttk.Frame(self.root)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=4, pady=4)

        ttk.Button(toolbar, text="➕ Добавить", command=self.add_site).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="➖ Удалить", command=self.remove_site).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        self.start_btn = ttk.Button(toolbar, text="▶ Старт", command=self.start_monitoring)
        self.start_btn.pack(side=tk.LEFT, padx=2)
        self.stop_btn = ttk.Button(toolbar, text="⏹ Стоп", command=self.stop_monitoring, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="⚡ Проверить сейчас", command=self.check_now).pack(side=tk.LEFT, padx=2)

        ttk.Label(toolbar, text="Интервал (с):").pack(side=tk.LEFT, padx=(10, 2))
        self.interval_var = tk.IntVar(value=DEFAULT_INTERVAL)
        ttk.Spinbox(toolbar, from_=5, to=3600, width=6,
                    textvariable=self.interval_var).pack(side=tk.LEFT)

        self.theme_btn = ttk.Button(toolbar, text="🌙 Ночь", command=self.toggle_theme)
        self.theme_btn.pack(side=tk.RIGHT, padx=2)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.build_sites_tab()
        self.build_history_tab()
        self.build_chart_tab()
        self.build_report_tab()

        self.status_var = tk.StringVar(value="Готово к работе")
        ttk.Label(self.root, textvariable=self.status_var,
                  anchor=tk.W).pack(side=tk.BOTTOM, fill=tk.X)

    def build_sites_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="📋 Сайты")
        cols = ('name', 'url', 'status', 'code', 'time', 'checked')
        self.sites_tree = ttk.Treeview(tab, columns=cols, show='headings')
        headers = {
            'name': ('Название', 150), 'url': ('URL', 400),
            'status': ('Статус', 100), 'code': ('HTTP', 80),
            'time': ('Время (мс)', 110), 'checked': ('Проверен', 160),
        }
        for c, (h, w) in headers.items():
            self.sites_tree.heading(c, text=h)
            self.sites_tree.column(c, width=w, anchor=tk.W)
        vsb = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=self.sites_tree.yview)
        self.sites_tree.configure(yscrollcommand=vsb.set)
        self.sites_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

    def build_history_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="📜 История")
        top = ttk.Frame(tab)
        top.pack(fill=tk.X, padx=4, pady=4)
        ttk.Label(top, text="Сайт:").pack(side=tk.LEFT)
        self.history_url_var = tk.StringVar()
        self.history_combo = ttk.Combobox(top, textvariable=self.history_url_var,
                                          state='readonly', width=50)
        self.history_combo.pack(side=tk.LEFT, padx=4)
        self.history_combo.bind('<<ComboboxSelected>>', lambda e: self.refresh_history())
        ttk.Button(top, text="Обновить", command=self.refresh_history).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Очистить историю", command=self.clear_history).pack(side=tk.LEFT, padx=4)

        cols = ('ts', 'name', 'url', 'status', 'code', 'time')
        self.history_tree = ttk.Treeview(tab, columns=cols, show='headings')
        headers = {
            'ts': ('Время', 160), 'name': ('Название', 140), 'url': ('URL', 380),
            'status': ('Статус', 100), 'code': ('HTTP', 70), 'time': ('Время (мс)', 100),
        }
        for c, (h, w) in headers.items():
            self.history_tree.heading(c, text=h)
            self.history_tree.column(c, width=w, anchor=tk.W)
        vsb = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=vsb.set)
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

    def build_chart_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="📈 График")
        top = ttk.Frame(tab)
        top.pack(fill=tk.X, padx=4, pady=4)
        ttk.Label(top, text="Сайт:").pack(side=tk.LEFT)
        self.chart_url_var = tk.StringVar()
        self.chart_combo = ttk.Combobox(top, textvariable=self.chart_url_var,
                                        state='readonly', width=50)
        self.chart_combo.pack(side=tk.LEFT, padx=4)
        ttk.Label(top, text="За последние:").pack(side=tk.LEFT, padx=(10, 2))
        self.chart_hours_var = tk.IntVar(value=24)
        ttk.Spinbox(top, from_=1, to=720, width=6,
                    textvariable=self.chart_hours_var).pack(side=tk.LEFT)
        ttk.Label(top, text="ч").pack(side=tk.LEFT)
        ttk.Button(top, text="Построить", command=self.draw_chart).pack(side=tk.LEFT, padx=6)

        if HAS_MPL:
            self.fig = Figure(figsize=(8, 4), dpi=90)
            self.ax = self.fig.add_subplot(111)
            self.canvas = FigureCanvasTkAgg(self.fig, master=tab)
            self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        else:
            ttk.Label(tab, text="Для графиков установите: pip install matplotlib"
                      ).pack(pady=20)

    def build_report_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="📄 Отчёт")
        top = ttk.Frame(tab)
        top.pack(fill=tk.X, padx=4, pady=4)
        ttk.Label(top, text="Период (часов):").pack(side=tk.LEFT)
        self.report_hours_var = tk.IntVar(value=24)
        ttk.Spinbox(top, from_=1, to=720, width=6,
                    textvariable=self.report_hours_var).pack(side=tk.LEFT)
        ttk.Button(top, text="Сформировать", command=self.generate_report).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Экспорт CSV", command=self.export_csv).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Экспорт HTML", command=self.export_html).pack(side=tk.LEFT, padx=2)

        self.report_text = tk.Text(tab, wrap='word', font=('Consolas', 10))
        vsb = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=self.report_text.yview)
        self.report_text.configure(yscrollcommand=vsb.set)
        self.report_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

    # ---------- Тема ----------
    def apply_theme(self):
        t = THEMES[self.theme_name]
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except Exception:
            pass

        self.root.configure(bg=t['bg'])
        style.configure('.', background=t['bg'], foreground=t['fg'], fieldbackground=t['field'])
        style.configure('TFrame', background=t['bg'])
        style.configure('TLabel', background=t['bg'], foreground=t['fg'])
        style.configure('TButton', background=t['button'], foreground=t['button_fg'])
        style.map('TButton', background=[('active', t['accent'])],
                  foreground=[('active', 'white')])
        style.configure('TNotebook', background=t['bg'], borderwidth=0)
        style.configure('TNotebook.Tab', background=t['button'],
                        foreground=t['button_fg'], padding=[10, 4])
        style.map('TNotebook.Tab',
                  background=[('selected', t['accent'])],
                  foreground=[('selected', 'white')])
        style.configure('Treeview', background=t['field'],
                        fieldbackground=t['field'], foreground=t['fg'])
        style.configure('Treeview.Heading', background=t['header'], foreground='white')
        style.map('Treeview', background=[('selected', t['select'])],
                  foreground=[('selected', t['select_fg'])])
        for w in ('TCombobox', 'TSpinbox', 'TEntry'):
            style.configure(w, fieldbackground=t['field'], foreground=t['fg'],
                            background=t['field'])

        # Цветные теги
        self.sites_tree.tag_configure('ok', foreground=t['ok'])
        self.sites_tree.tag_configure('fail', foreground=t['error'])
        self.sites_tree.tag_configure('error', foreground=t['warn'])
        self.history_tree.tag_configure('ok', foreground=t['ok'])
        self.history_tree.tag_configure('fail', foreground=t['error'])
        self.history_tree.tag_configure('error', foreground=t['warn'])

        self.report_text.configure(bg=t['field'], fg=t['fg'],
                                   insertbackground=t['fg'])

        if hasattr(self, 'fig'):
            self.fig.patch.set_facecolor(t['chart_bg'])
            self.ax.set_facecolor(t['chart_bg'])
            for spine in self.ax.spines.values():
                spine.set_color(t['chart_fg'])
            self.ax.tick_params(colors=t['chart_fg'])
            self.ax.xaxis.label.set_color(t['chart_fg'])
            self.ax.yaxis.label.set_color(t['chart_fg'])
            self.ax.title.set_color(t['chart_fg'])
            self.canvas.draw()

    def toggle_theme(self):
        self.theme_name = 'dark' if self.theme_name == 'light' else 'light'
        self.theme_btn.configure(text='☀ День' if self.theme_name == 'dark' else '🌙 Ночь')
        self.apply_theme()
        if HAS_MPL and self.chart_url_var.get():
            self.draw_chart()

    # ---------- Список сайтов ----------
    def refresh_site_tree(self):
        self.sites_tree.delete(*self.sites_tree.get_children())
        for s in self.sites:
            self.sites_tree.insert('', tk.END, iid=s['url'],
                                   values=(s['name'], s['url'], '-', '-', '-', '-'))
        self.refresh_combos()

    def refresh_combos(self):
        urls = [s['url'] for s in self.sites]
        self.history_combo['values'] = urls
        self.chart_combo['values'] = urls
        if urls:
            if self.history_url_var.get() not in urls:
                self.history_url_var.set(urls[0])
            if self.chart_url_var.get() not in urls:
                self.chart_url_var.set(urls[0])

    def add_site(self):
        name = simpledialog.askstring("Добавить сайт", "Название:", parent=self.root)
        if not name:
            return
        url = simpledialog.askstring("Добавить сайт",
                                     "URL (например https://example.com):",
                                     parent=self.root)
        if not url:
            return
        url = url.strip()
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        self.sites.append({'name': name.strip(), 'url': url})
        self.save_sites()
        self.refresh_site_tree()

    def remove_site(self):
        sel = self.sites_tree.selection()
        if not sel:
            return
        url = sel[0]
        self.sites = [s for s in self.sites if s['url'] != url]
        self.save_sites()
        self.refresh_site_tree()

    # ---------- Мониторинг ----------
    def start_monitoring(self):
        if self.running:
            return
        self.running = True
        self.interval = max(5, self.interval_var.get())
        self.stop_event.clear()
        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        self.status_var.set(f"Мониторинг запущен (интервал {self.interval} с)")
        threading.Thread(target=self.check_loop, daemon=True).start()

    def stop_monitoring(self):
        if not self.running:
            return
        self.running = False
        self.stop_event.set()
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self.status_var.set("Мониторинг остановлен")

    def check_now(self):
        if self.running:
            return
        threading.Thread(target=self.single_check_worker, daemon=True).start()

    def single_check_worker(self):
        for site in list(self.sites):
            r = self.check_site(site)
            self.save_result(r)
            self.result_queue.put(r)

    def check_loop(self):
        while not self.stop_event.is_set():
            for site in list(self.sites):
                if self.stop_event.is_set():
                    break
                r = self.check_site(site)
                self.save_result(r)
                self.result_queue.put(r)
            end = time.time() + self.interval
            while time.time() < end:
                if self.stop_event.is_set():
                    break
                time.sleep(0.2)

    def check_site(self, site):
        url = site['url']
        ts = datetime.datetime.now()
        try:
            start = time.time()
            resp = requests.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True,
                                headers={'User-Agent': 'SiteMonitor/1.0'})
            elapsed_ms = round((time.time() - start) * 1000, 1)
            ok = 200 <= resp.status_code < 400
            return {
                'name': site['name'], 'url': url,
                'status': 'OK' if ok else 'FAIL',
                'code': resp.status_code, 'time_ms': elapsed_ms,
                'error': None, 'timestamp': ts,
            }
        except requests.exceptions.RequestException as e:
            return {
                'name': site['name'], 'url': url,
                'status': 'ERROR', 'code': None, 'time_ms': None,
                'error': str(e)[:200], 'timestamp': ts,
            }

    def save_result(self, r):
        with self.db_lock:
            self.conn.execute(
                "INSERT INTO history(timestamp, name, url, status, code, time_ms, error) "
                "VALUES (?,?,?,?,?,?,?)",
                (r['timestamp'].isoformat(timespec='seconds'),
                 r['name'], r['url'], r['status'],
                 r['code'], r['time_ms'], r['error'])
            )
            self.conn.commit()

    def poll_results(self):
        try:
            while True:
                r = self.result_queue.get_nowait()
                self.apply_result(r)
        except queue.Empty:
            pass
        self.root.after(200, self.poll_results)

    def apply_result(self, r):
        tag = {'OK': 'ok', 'FAIL': 'fail', 'ERROR': 'error'}.get(r['status'], '')
        vals = (r['name'], r['url'], r['status'],
                r['code'] if r['code'] is not None else '-',
                f"{r['time_ms']:.1f}" if r['time_ms'] is not None else '-',
                r['timestamp'].strftime('%Y-%m-%d %H:%M:%S'))
        if self.sites_tree.exists(r['url']):
            self.sites_tree.item(r['url'], values=vals, tags=(tag,))
        self.status_var.set(
            f"Проверено: {r['name']} → {r['status']} "
            f"({r['code']}) в {r['timestamp'].strftime('%H:%M:%S')}"
        )

    # ---------- История ----------
    def refresh_history(self):
        url = self.history_url_var.get()
        if not url:
            return
        with self.db_lock:
            cur = self.conn.execute(
                "SELECT timestamp, name, url, status, code, time_ms FROM history "
                "WHERE url=? ORDER BY id DESC LIMIT 500", (url,))
            rows = cur.fetchall()
        self.history_tree.delete(*self.history_tree.get_children())
        for row in rows:
            tag = 'ok' if row[3] == 'OK' else ('fail' if row[3] == 'FAIL' else 'error')
            self.history_tree.insert('', tk.END, values=(
                row[0], row[1], row[2], row[3],
                row[4] if row[4] is not None else '-',
                row[5] if row[5] is not None else '-'
            ), tags=(tag,))

    def clear_history(self):
        if not messagebox.askyesno("Очистка", "Удалить всю историю?"):
            return
        with self.db_lock:
            self.conn.execute("DELETE FROM history")
            self.conn.commit()
        self.refresh_history()

    # ---------- График ----------
    def draw_chart(self):
        if not HAS_MPL:
            return
        url = self.chart_url_var.get()
        if not url:
            return
        hours = self.chart_hours_var.get()
        since = (datetime.datetime.now() -
                 datetime.timedelta(hours=hours)).isoformat(timespec='seconds')
        with self.db_lock:
            cur = self.conn.execute(
                "SELECT timestamp, time_ms, status FROM history "
                "WHERE url=? AND timestamp>=? ORDER BY timestamp", (url, since))
            rows = cur.fetchall()

        t = THEMES[self.theme_name]
        self.ax.clear()
        self.ax.set_facecolor(t['chart_bg'])
        self.fig.patch.set_facecolor(t['chart_bg'])

        if not rows:
            self.ax.text(0.5, 0.5, "Нет данных за выбранный период",
                         ha='center', va='center', color=t['chart_fg'],
                         transform=self.ax.transAxes, fontsize=12)
        else:
            times = [datetime.datetime.fromisoformat(r[0]) for r in rows]
            vals = [r[1] if r[1] is not None else float('nan') for r in rows]
            self.ax.plot(times, vals, marker='o', markersize=3,
                         color=t['accent'], linewidth=1.4, label='Время ответа')

            valid_vals = [v for v in vals if v == v]
            if valid_vals:
                ymark = max(valid_vals) * 0.95 if max(valid_vals) > 0 else 1
                fail_times = [datetime.datetime.fromisoformat(r[0])
                              for r in rows if r[2] != 'OK']
                if fail_times:
                    self.ax.scatter(fail_times, [ymark] * len(fail_times),
                                    color=t['error'], marker='x', s=50,
                                    label='Ошибки', zorder=5)

            self.ax.set_title(f"Время ответа: {url}")
            self.ax.set_xlabel("Время")
            self.ax.set_ylabel("мс")
            self.ax.grid(True, color=t['chart_grid'], linestyle='--', alpha=0.5)

            leg = self.ax.legend(facecolor=t['chart_bg'],
                                 edgecolor=t['chart_fg'], loc='upper left')
            if leg:
                for txt in leg.get_texts():
                    txt.set_color(t['chart_fg'])

            locator = mdates.AutoDateLocator()
            formatter = mdates.DateFormatter('%H:%M')
            self.ax.xaxis.set_major_locator(locator)
            self.ax.xaxis.set_major_formatter(formatter)
            self.fig.autofmt_xdate()

        for spine in self.ax.spines.values():
            spine.set_color(t['chart_fg'])
        self.ax.tick_params(colors=t['chart_fg'])
        self.canvas.draw()

    # ---------- Отчёт ----------
    def generate_report(self):
        hours = self.report_hours_var.get()
        since = (datetime.datetime.now() -
                 datetime.timedelta(hours=hours)).isoformat(timespec='seconds')
        with self.db_lock:
            cur = self.conn.execute("""
                SELECT url, name, COUNT(*),
                       SUM(CASE WHEN status='OK' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN status!='OK' THEN 1 ELSE 0 END),
                       AVG(time_ms), MIN(time_ms), MAX(time_ms)
                FROM history WHERE timestamp>=?
                GROUP BY url ORDER BY url
            """, (since,))
            rows = cur.fetchall()

        lines = ["=" * 78,
                 "       ОТЧЁТ О ДОСТУПНОСТИ САЙТОВ",
                 f"       Период: последние {hours} ч.",
                 f"       Сформирован: "
                 f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                 "=" * 78, ""]
        if not rows:
            lines.append("Нет данных за указанный период.")
        else:
            for url, name, total, ok, fail, avg_t, min_t, max_t in rows:
                pct = 100.0 * ok / total if total else 0
                lines.append(f"🌐 {name}  —  {url}")
                lines.append(f"   Проверок: {total} | OK: {ok} | Ошибок: {fail} "
                             f"| Доступность: {pct:.1f}%")
                if avg_t is not None:
                    lines.append(f"   Время ответа (мс): среднее={avg_t:.1f}, "
                                 f"min={min_t}, max={max_t}")
                lines.append("")
        self.report_text.delete('1.0', tk.END)
        self.report_text.insert('1.0', "\n".join(lines))

    def export_csv(self):
        hours = self.report_hours_var.get()
        since = (datetime.datetime.now() -
                 datetime.timedelta(hours=hours)).isoformat(timespec='seconds')
        path = filedialog.asksaveasfilename(defaultextension='.csv',
                                            filetypes=[('CSV', '*.csv')])
        if not path:
            return
        with self.db_lock:
            cur = self.conn.execute(
                "SELECT timestamp, name, url, status, code, time_ms, error "
                "FROM history WHERE timestamp>=? ORDER BY timestamp", (since,))
            rows = cur.fetchall()
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f, delimiter=';')
            w.writerow(['timestamp', 'name', 'url', 'status', 'code',
                        'time_ms', 'error'])
            for row in rows:
                w.writerow(row)
        messagebox.showinfo("Экспорт", f"Сохранено в:\n{path}")

    def export_html(self):
        hours = self.report_hours_var.get()
        since = (datetime.datetime.now() -
                 datetime.timedelta(hours=hours)).isoformat(timespec='seconds')
        with self.db_lock:
            cur = self.conn.execute("""
                SELECT url, name, COUNT(*),
                       SUM(CASE WHEN status='OK' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN status!='OK' THEN 1 ELSE 0 END),
                       AVG(time_ms), MIN(time_ms), MAX(time_ms)
                FROM history WHERE timestamp>=?
                GROUP BY url ORDER BY url
            """, (since,))
            rows = cur.fetchall()
        path = filedialog.asksaveasfilename(defaultextension='.html',
                                            filetypes=[('HTML', '*.html')])
        if not path:
            return
        html = [
            "<html><head><meta charset='utf-8'><title>Отчёт мониторинга</title>",
            "<style>body{font-family:system-ui;padding:20px;background:#fafafa;color:#333}"
            "table{border-collapse:collapse;width:100%}"
            "th,td{border:1px solid #ccc;padding:6px 10px;text-align:left}"
            "th{background:#3498db;color:#fff}tr:nth-child(even){background:#f0f6ff}"
            ".ok{color:#27ae60;font-weight:bold}"
            ".fail{color:#e74c3c;font-weight:bold}</style></head><body>",
            "<h1>Отчёт о доступности сайтов</h1>",
            f"<p>Период: последние <b>{hours}</b> ч. "
            f"Сформирован: {datetime.datetime.now():%Y-%m-%d %H:%M:%S}</p>",
            "<table><tr><th>Название</th><th>URL</th><th>Проверок</th>"
            "<th>OK</th><th>Ошибок</th><th>Доступность</th>"
            "<th>Avg (мс)</th><th>Min</th><th>Max</th></tr>"
        ]
        for url, name, total, ok, fail, avg_t, min_t, max_t in rows:
            pct = 100.0 * ok / total if total else 0
            cls = 'ok' if pct >= 95 else ('fail' if pct < 80 else '')
            avg_s = f"{avg_t:.1f}" if avg_t is not None else ''
            min_s = f"{min_t}" if min_t is not None else ''
            max_s = f"{max_t}" if max_t is not None else ''
            html.append(
                f"<tr><td>{name}</td><td>{url}</td><td>{total}</td>"
                f"<td>{ok}</td><td>{fail}</td>"
                f"<td class='{cls}'>{pct:.1f}%</td>"
                f"<td>{avg_s}</td><td>{min_s}</td><td>{max_s}</td></tr>"
            )
        html.append("</table></body></html>")
        with open(path, 'w', encoding='utf-8') as f:
            f.write("\n".join(html))
        messagebox.showinfo("Экспорт", f"Отчёт сохранён в:\n{path}")

    # ---------- Завершение ----------
    def on_close(self):
        self.running = False
        self.stop_event.set()
        try:
            self.conn.close()
        except Exception:
            pass
        self.root.destroy()


def main():
    root = tk.Tk()
    SiteMonitorApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()