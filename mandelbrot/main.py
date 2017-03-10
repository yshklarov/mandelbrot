#!/usr/bin/env python3

import os
import sys
import numbers
import math
import multiprocessing
import queue
import threading
import functools
import tkinter as tk
import tkinter.messagebox as tkmb

import pygame
import mpmath
from mpmath import mp, mpc

import worker


PROGRAM_NAME = "Mandelbrot"
WINDOW_WIDTH = 400
WINDOW_HEIGHT = 418

DEFAULT_MAX_ITERATIONS = 500
RE_MIN = IM_MIN = -2
RE_MAX = IM_MAX = 2

WORKERS = 8

# Set the number of passes for progressive rendering. Keep this number fairly low to avoid flicker.
PASSES = 6

# This is quite slow, but it's required if you'd like to zoom further than (10^12)x or so.
# Precision is not actually arbitrary during runtime but can be increased in 'mandelbrot.py'.
ARBITRARY_PRECISION = False
worker.set_arbitrary_precision(ARBITRARY_PRECISION)


class Viewport:    

    def __init__(self, window_id):
        # The window referenced by window_id must exist (eg. call root.update() in tkinter)
        self.width, self.height = 0, 0
        if ARBITRARY_PRECISION:
            self.center = mp.mpc(0)
        else:
            self.center = 0
        self.zoom = 1
        self.max_iterations = DEFAULT_MAX_ITERATIONS

        self.size_q = multiprocessing.Queue()
        self.location_q = multiprocessing.Queue()
        self.max_iterations_q = multiprocessing.Queue()

        self.render_event = multiprocessing.Event()
        self.refresh_event = multiprocessing.Event()
        self.redraw_q = multiprocessing.Queue()
        self.redraw_scheduled = False
        self.stop_event = multiprocessing.Event()
        self.quit_event = multiprocessing.Event()

        self.status_callbacks = []

        self.render_p = multiprocessing.Process(target=self.render, args=[window_id])
        self.render_p.start()

    def register_status_callback(self, cb):
        self.status_callbacks.append(cb)

    def update_status(self):
        for cb in self.status_callbacks:
            cb(self.status_string())

    def status_string(self):
        return '{:.8} + {:.8}i (Zoom = {:.3g})'.format(
                float(self.center.real), float(self.center.imag), self.zoom)

    def set_size(self, width, height):
        if (self.width, self.height) != (width, height):
            self.width = width
            self.height = height
            self.size_q.put((self.width, self.height))
            self.stop_event.set()
            self.redraw_delayed(0)
        self.update_status()

    def set_max_iterations(self, max_iterations):
        if (self.max_iterations != max_iterations
                and max_iterations >= 0):
            self.max_iterations = max_iterations
            self.max_iterations_q.put(max_iterations)
            self.redraw()

    def location(self):
        return (self.center, self.zoom)

    def go_to_location(self, center, zoom=None):
        self.center = center
        if zoom is not None:
            self.zoom = zoom
        self.location_q.put((self.center, self.zoom))
        self.update_status()
        self.redraw()

    def drag_begin(self, x, y):
        self.drag_from = self.xy_to_complex(x, y)

    def drag_end(self, x, y):
        drag_mod = self.xy_to_complex(x, y) - self.drag_from
        if drag_mod != 0:
            self.go_to_location(self.center - drag_mod)

    def zoom_in(self, x=None, y=None):
        self.dilate(0.5, x, y)

    def zoom_out(self, x=None, y=None):
        self.dilate(2, x, y)
    
    def dilate(self, ratio, x=None, y=None):
        if x is None:
            x = self.width // 2
        if y is None:
            y = self.height // 2
        center_of_dilation = self.xy_to_complex(x, y)
        new_center = center_of_dilation + (self.center - center_of_dilation)*ratio
        self.go_to_location(new_center, self.zoom/ratio)

    def xy_to_complex(self, x, y):
        x_rel = (x - self.width // 2)
        y_rel = -(y - self.height // 2)
        # Keep aspect ratio at 1:1.
        size = max(self.width, self.height)
        if ARBITRARY_PRECISION:
            offset = mp.mpc(x_rel * (RE_MAX - RE_MIN),
                            y_rel * (IM_MAX - IM_MIN)) / (self.zoom * size)
        else:
            offset = ((x_rel * (RE_MAX - RE_MIN))
                    + 1j*(y_rel * (IM_MAX - IM_MIN))) / (self.zoom * size)
        return self.center + offset

    def refresh(self):
        # Re-paint the window surface (without rendering anew.)
        self.refresh_event.set()

    def refresh_watchdog(self):
        while self.refresh_event.wait():
            self.refresh_event.clear()
            pygame.display.update()

    def close(self):
        # Clean up all child processes.
        self.quit_event.set()
        self.stop_event.set()
        self.render_event.set()  # Release block in render()

    def redraw_delayed(self, delay):
        # Call redraw() after the given delay (in seconds). Repeat calls reset the delay to
        # the new value. Do not block.
        if not self.redraw_scheduled:
            def wait(delay):
                while True:
                    try:
                        delay = self.redraw_q.get(timeout=delay)
                    except queue.Empty as e:  # Timeout reached
                        self.redraw_scheduled = False
                        self.redraw()
                        break
            self.redraw_scheduled = True
            t = threading.Thread(target=wait, daemon=True, args=[delay])
            t.start()
        else:
            self.redraw_q.put(delay)

    def redraw(self):
        # Re-render immediately. Block until rendering has begun anew.
        self.stop_event.set()
        self.render_event.set()

    def render(self, window_id):
        os.environ['SDL_WINDOWID'] = str(window_id)
        self.canvas = pygame.display.set_mode()
        pygame.display.init()
        threading.Thread(target=self.refresh_watchdog, daemon=True).start()

        while not self.quit_event.is_set():
            with multiprocessing.Pool(processes=WORKERS) as pool:
                self.render_event.wait()
                if self.quit_event.is_set():
                    break
                self.render_event.clear()
                self.stop_event.clear()

                # Get new size if changed
                try:
                    while True:
                        self.width, self.height = self.size_q.get_nowait()
                except queue.Empty as e: pass

                # Get new location if changed
                try:
                    while True:
                        self.center, self.zoom = self.location_q.get_nowait()
                except queue.Empty as e: pass

                # Get new max_iterations if changed
                try:
                    while True:
                        self.max_iterations = self.max_iterations_q.get_nowait()
                except queue.Empty as e: pass

                self.canvas.fill((0, 0, 0), pygame.Rect(0, 0, self.width, self.height))

                max_pitch = 2 ** (PASSES - 1)
                res = [self.xy_to_complex(x, 0).real
                       for x in range(0, self.width + max_pitch // 2 - 1)]
                ims = [1j*self.xy_to_complex(0, y).imag
                       for y in range(0, self.height + max_pitch // 2 - 1)]

                work = []
                for i in range(0, PASSES):
                    pitch = 2 ** (PASSES - i - 1)
                    for x in range(0, self.width + pitch // 2 - 1, pitch):
                        # Don't repeat work that's been done on a previous pass.
                        y_first = 0
                        y_pitch = pitch
                        if i > 0:
                            if x % (pitch * 2) == 0:
                                y_first = y_pitch
                                y_pitch *= 2
                        work.append((x,
                                     range(y_first, self.height + pitch // 2 - 1, y_pitch),
                                     res,
                                     ims,
                                     pitch))
                jobs = pool.imap_unordered(worker.worker(self.max_iterations), work)

                for job in jobs:
                    for (x, y, iterations_to_escape, pitch) in job:
                        rect = (x - pitch // 2, y - pitch // 2, pitch, pitch)
                        self.canvas.fill(self.colormap(iterations_to_escape), rect)
                    pygame.display.update()
                    if self.stop_event.is_set():
                        pool.terminate()
                        break

    # Memoizing isn't useful with color smoothing since n is not an integer.
    #@functools.lru_cache(maxsize=5000)
    def colormap(self, n):
        if n > self.max_iterations:
            return (0, 0, 0)
        r = math.floor(self.triangle_wave(n, 30) * 255)
        g = math.floor(self.triangle_wave(n, 100) * 255)
        b = math.floor(self.triangle_wave(n, 400) * 255)
        return (r, g, b)

    def triangle_wave(self, x, period):
        # Triangle wave with range from 0 to 1.
        return 2 * abs(x/period - round(x/period))


def widget_size(widget):
    return (widget.winfo_width(), widget.winfo_height())

def controls_handler(_=None):
    tkmb.showinfo(title="Controls", message="Drag to move; scroll to zoom")

def about_handler(_=None):
    tkmb.showinfo(title="Mandelbrot", message="Copyright (c) 2017 Yakov Shklarov")

def save_location_handler(root):
    location = str(viewport.location())
    if tkmb.askyesno(title="Save location", message=location + ": Copy to clipboard?"):
        root.clipboard_clear()
        root.clipboard_append(location)

def go_to_location_handler(viewport):
    try:
        # TODO dangerous! But for now it must work with the mpc type.
        location = eval(root.clipboard_get())
        if (not isinstance(location, tuple)) or (len(location) != 2):
            raise ValueError
        (center, zoom) = location
        if not (isinstance(center, mpmath.mpc) or isinstance(center, numbers.Complex)) \
           or not isinstance(zoom, numbers.Real):
            raise ValueError
    except (ValueError, SyntaxError, tk.TclError) as e:
        tkmb.showerror(title="Invalid location", message="Clipboard must contain a location.")
    else:
        if tkmb.askyesno(title="Go to location", message=
                         "Go to {} (zoom {})?".format(center, zoom)):
            viewport.go_to_location(center, zoom)

def reset_zoom_handler(viewport):
    viewport.go_to_location(0+0j, 1)

def set_iterations_handler(root, viewport):
    dialog = tk.Toplevel(root)
    dialog.title("Set iterations")
    #dialog.transient(root)
    dialog.resizable(False, False)
    tk.Label(dialog, text="Maximum iterations:").grid(row=0, column=0, sticky='e')
    # TODO validate input; use tk variable
    entry_box = tk.Entry(dialog, width=6, text="foo")
    entry_box.grid(row=0, column=1, padx=2, pady=2, sticky='we')
    entry_box.delete(0, len(entry_box.get()))
    entry_box.insert(0, viewport.max_iterations)
    dialog.focus_set()
    def set_max_iterations():
        viewport.set_max_iterations(int(entry_box.get()))
    def close_dialog():
        dialog.destroy()
    tk.Button(dialog, text="Set", underline=0, command=set_max_iterations).grid(
        row=0, column=2, sticky='e' + 'w', padx=2, pady=2)
    tk.Button(dialog, text="Close", underline=0, command=close_dialog).grid(
        row=0, column=3, sticky='e' + 'w', padx=2, pady=2)
    dialog.protocol('WM_DELETE_WINDOW', close_dialog)


if __name__ == "__main__":
    # TODO Fix bugs when start method is not spawn
    multiprocessing.set_start_method('spawn')

    root = tk.Tk()
    root.title(PROGRAM_NAME)
    root.geometry('{}x{}'.format(WINDOW_WIDTH, WINDOW_HEIGHT))

    menu_bar = tk.Menu(root)
    root.config(menu=menu_bar)

    embed = tk.Frame(root, bg='black')
    embed.pack(expand=1, fill=tk.BOTH)

    root.update()  # Create embed frame before calling Viewport()
    viewport = Viewport(embed.winfo_id())

    status = tk.StringVar()
    viewport.register_status_callback(status.set)
    status_bar = tk.Label(root, bd=1, relief=tk.SUNKEN, anchor=tk.W, height=1, textvariable=status)
    status_bar.pack(fill=tk.X)

    file_menu = tk.Menu(menu_bar, tearoff=0)
    view_menu = tk.Menu(menu_bar, tearoff=0)
    help_menu = tk.Menu(menu_bar, tearoff=0)
    menu_bar.add_cascade(label='File', menu=file_menu)
    menu_bar.add_cascade(label='View', menu=view_menu)
    menu_bar.add_cascade(label='Help', menu=help_menu)

    file_menu.add_command(label='Save location...', command=
                          functools.partial(save_location_handler, root))
    file_menu.add_command(label='Go to location...', command=
                          functools.partial(go_to_location_handler, viewport))
    file_menu.insert_separator(2)
    file_menu.add_command(label='Quit', accelerator='q', command=root.quit)

    view_menu.add_command(label='Zoom In', accelerator='+', command=viewport.zoom_in)
    view_menu.add_command(label='Zoom Out', accelerator='-', command=viewport.zoom_out)
    view_menu.add_command(label='Reset Zoom', command=
                          functools.partial(reset_zoom_handler, viewport))
    view_menu.insert_separator(3)
    view_menu.add_command(label='Redraw', accelerator='r', command=viewport.redraw)
    view_menu.insert_separator(5)
    view_menu.add_command(label='Set iterations...', command=
                          functools.partial(set_iterations_handler, root, viewport))

    help_menu.add_command(label='Controls', accelerator='F1', command=controls_handler)
    help_menu.add_command(label='About', command=about_handler)

    root.bind_all('q', lambda _: root.quit())
    root.bind_all('r', lambda _: viewport.redraw())
    root.bind_all('<Key-F1>', controls_handler)
    root.bind_all('<KP_Add>', lambda _: viewport.zoom_in())
    root.bind_all('<plus>', lambda _: viewport.zoom_in())
    root.bind_all('<KP_Subtract>', lambda _: viewport.zoom_out())
    root.bind_all('<minus>', lambda _: viewport.zoom_out())
    embed.bind('<Button-4>', lambda ev: viewport.zoom_in(x=ev.x, y=ev.y))
    embed.bind('<Button-5>', lambda ev: viewport.zoom_out(x=ev.x, y=ev.y))
    embed.bind('<Button-1>', lambda ev: viewport.drag_begin(ev.x, ev.y))
    embed.bind('<ButtonRelease-1>', lambda ev: viewport.drag_end(ev.x, ev.y))

    # <Configure> gets called on widget resize
    embed.bind('<Configure>', lambda _: viewport.set_size(*widget_size(embed)))
    embed.bind('<Visibility>', lambda _: embed.after(1, viewport.refresh))
    root.protocol('WM_DELETE_WINDOW', root.quit)

    root.mainloop()

    viewport.close()
