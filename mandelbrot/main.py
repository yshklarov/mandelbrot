#!/usr/bin/env python3

import os
import sys
import time
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
DEFAULT_ARBITRARY_PRECISION = False
RE_MIN = IM_MIN = -2
RE_MAX = IM_MAX = 2

# If WORKERS is None then os.cpucount() is used.
WORKERS = None
#WORKERS = 8

# Set the number of passes for progressive rendering. Keep this number fairly low to avoid flicker.
PASSES = 6


class Viewport:    

    def __init__(self, window_id, dimensions=(0, 0)):
        # The window referenced by window_id must exist (eg. call root.update() in tkinter)

        self.window_id = window_id
        self.dimensions = dimensions
        self.center = complex(0)
        self.zoom = float(1)
        self.max_iterations = DEFAULT_MAX_ITERATIONS
        self.arbitrary_precision = DEFAULT_ARBITRARY_PRECISION

        self.status_callbacks = []

        # Correctly initialize types
        self.set_arbitrary_precision(
            self.arbitrary_precision,
            force=True,
            update_render=False,
            )
        self.render_p = RenderProcess(window_id)
        self.render_p.start()
        self.update_render_p()

    def update_render_p(self, redraw=True):
        if redraw:
            self.render_p.stop()
        self.render_p.update(
            dimensions=self.dimensions,
            maps=(self.re_map, self.im_map),
            max_iterations=self.max_iterations,
            arbitrary_precision=self.arbitrary_precision,
            )
        if redraw:
            self.render_p.go()

    def register_status_callback(self, cb):
        self.status_callbacks.append(cb)

    def update_status(self):
        for cb in self.status_callbacks:
            cb(self.status_string())

    def status_string(self):
        return '{:.8} + {:.8}i (Zoom = {:.3g})'.format(
                float(self.center.real), float(self.center.imag), self.zoom)

    def set_dimensions(self, dimensions):
        # dimensions: tuple (width, height), width and height in pixels.
        if self.dimensions != dimensions:
            self.dimensions = dimensions
            self._rebuild_maps()
            self.update_render_p()
            self.update_status()

    def set_max_iterations(self, max_iterations):
        if (self.max_iterations != max_iterations
                and max_iterations >= 0):
            self.max_iterations = max_iterations
            self.update_render_p()

    def set_arbitrary_precision(self, arbitrary_precision, force=False, update_render=True):
        """ arbitrary_precision: bool """
        # Precision is not actually arbitrary during runtime but can be increased in
        # 'mandelbrot.py'.
        if (self.arbitrary_precision == arbitrary_precision
                and not force):
            return
        self.arbitrary_precision = arbitrary_precision
        if self.arbitrary_precision:
            self._complex = mp.mpc
            self.center = mp.mpc(self.center)
        else:
            self._complex = complex
            self.center = complex(self.center)
        self._rebuild_maps()
        if update_render:
            self.update_render_p()

    def go_to_location(self, center=None, zoom=None):
        if center is not None:
            self.center = center
        if zoom is not None:
            self.zoom = zoom
        if (zoom is not None) or (center is not None):
            self._rebuild_maps()
            self.update_render_p()
            self.update_status()

    def location(self):
        return (self.center, self.zoom)

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
            x = self.dimensions[0] // 2
        if y is None:
            y = self.dimensions[1] // 2
        center_of_dilation = self.xy_to_complex(x, y)
        new_center = center_of_dilation + (self.center - center_of_dilation)*ratio
        self.go_to_location(new_center, self.zoom/ratio)

    def _rebuild_maps(self):
        self.re_map = [self.xy_to_complex(x, 0).real for x in range(0, self.dimensions[0])]
        self.im_map = [1j*self.xy_to_complex(0, y).imag for y in range(0, self.dimensions[1])]

    def xy_to_complex(self, x, y):
        x_rel = (x - self.dimensions[0] // 2)
        y_rel = -(y - self.dimensions[1] // 2)
        # Keep aspect ratio at 1:1.
        span = max(self.dimensions)
        offset = self._complex(x_rel * (RE_MAX - RE_MIN),
                               y_rel * (IM_MAX - IM_MIN)) / (self.zoom * span)
        return self.center + offset

    def redraw(self):
        self.render_p.restart()

    def stop(self):
        self.render_p.stop()

    def close(self):
        self.render_p.terminate()
        self.render_p.join()

    def refresh(self):
        # Re-paint the window surface, without stopping rendering or rendering anew.
        self.render_p.refresh()


class RenderProcess(multiprocessing.Process):

    def __init__(self, window_id):
        super().__init__()
        self.window_id = window_id
        self.render_event = multiprocessing.Event()
        self.rendering_event = multiprocessing.Event()
        self.idle_event = multiprocessing.Event()
        self.idle_event.set()
        self.refresh_event = multiprocessing.Event()
        self.stop_event = multiprocessing.Event()
        self.quit_event = multiprocessing.Event()
        self.event_lock = multiprocessing.Lock()

        self.dimensions = None
        self.maps = None
        self.max_iterations = None
        self.arbitrary_precision = None

        manager = multiprocessing.Manager()
        self.data = manager.dict()
        self.data_updated_event = multiprocessing.Event()
        self.data_lock = multiprocessing.Lock()

    def update(self, dimensions=None, maps=None, max_iterations=None, arbitrary_precision=None):
        with self.data_lock:
            self.data.update({
                'dimensions': dimensions,
                'maps': maps,
                'max_iterations': max_iterations,
                'arbitrary_precision': arbitrary_precision,
            })
        self.data_updated_event.set()

    def refresh(self):
        # Re-paint the window surface, without stopping rendering or rendering anew.
        self.refresh_event.set()

    def _refresh_watchdog(self):
        while self.refresh_event.wait():
            self.refresh_event.clear()
            pygame.display.update()

    def go(self):
        self.render_event.set()
        #self.rendering_event.wait()

    def stop(self):
        with self.event_lock:
            if self.rendering_event.is_set():
                self.stop_event.set()
        self.idle_event.wait()

    def restart(self):
        with self.event_lock:
            if self.rendering_event.is_set():
                self.stop_event.set()
            self.render_event.set()

    def terminate(self):
        # The RenderProcess will not terminate immediately; the caller should join() manually.
        with self.event_lock:
            self.quit_event.set()
            self.stop_event.set()
        self.render_event.set()  # Release block

    def run(self):
        os.environ['SDL_WINDOWID'] = str(self.window_id)
        self.canvas = pygame.display.set_mode()
        pygame.display.init()
        # We need this because we can't call pygame.display.update() from another different process.
        threading.Thread(target=self._refresh_watchdog, daemon=True).start()

        while not self.quit_event.is_set():
            # TODO Don't close and re-open pool, it's slow (takes up to 80 ms.)
            with multiprocessing.Pool(processes=WORKERS) as pool:
                self.render_event.wait()
                self.render_event.clear()

                if self.data_updated_event.is_set():
                    with self.data_lock:
                        if self.dimensions != self.data['dimensions']:
                             pygame.display.set_mode(self.data['dimensions'])
                        self.dimensions = self.data['dimensions']
                        self.maps = self.data['maps']
                        self.max_iterations = self.data['max_iterations']
                        self.arbitrary_precision = self.data['arbitrary_precision']
                        self.data_updated_event.clear()

                with self.event_lock:
                    if self.stop_event.is_set():
                        continue
                    self.rendering_event.set()
                    self.idle_event.clear()

                #print("Rendering... ", end='')
                #sys.stdout.flush()
                #t = time.time()
                self.canvas.fill((0, 0, 0), pygame.Rect(0, 0, *self.dimensions))
                work = []
                for i in range(0, PASSES):
                    pitch = 2 ** (PASSES - i - 1)
                    for x in range(0, self.dimensions[0], pitch):
                        # Don't repeat work that's been done on a previous pass.
                        y_first = 0
                        y_pitch = pitch
                        if i > 0:
                            if x % (pitch * 2) == 0:
                                y_first = y_pitch
                                y_pitch *= 2
                        work.append((x,
                                     range(y_first, self.dimensions[1], y_pitch),
                                     self.maps[0],
                                     self.maps[1],
                                     pitch))
                worker_func = worker.worker(self.max_iterations, self.arbitrary_precision)
                # Do not use imap_unordered here: it might cause earlier passes to overwrite later
                # ones. And besides: It looks glitchy.
                columns = pool.imap(worker_func, work, chunksize=1)

                for column in columns:
                    if self.stop_event.is_set():
                        # pool.terminate() often crashes during high precision. Why?
                        # TODO: This doesn't completely fix the crash.
                        pool.close()
                        break
                    for (x, y, iterations_to_escape, pitch) in column:
                        rect = (x - pitch // 2, y - pitch // 2, pitch, pitch)
                        self.canvas.fill(self._colormap(iterations_to_escape), rect)
                    pygame.display.update()
                #print("{:.6f}".format(time.time() - t))
                with self.event_lock:
                    self.stop_event.clear()
                    self.rendering_event.clear()
                self.idle_event.set()

    def _paint_column(self, column):
        print(len(column))
        print(column[0])
        sys.stdout.flush()
        for (x, y, iterations_to_escape, pitch) in column:
            rect = (x - pitch // 2, y - pitch // 2, pitch, pitch)
            self.canvas.fill(self._colormap(iterations_to_escape), rect)
        pygame.display.update()


    # Memoizing isn't useful with color smoothing since n is not an integer.
    #@functools.lru_cache(maxsize=5000)
    def _colormap(self, n):
        if n > self.max_iterations:
            return (0, 0, 0)
        r = math.floor(self._triangle_wave(n, 30) * 255)
        g = math.floor(self._triangle_wave(n, 100) * 255)
        b = math.floor(self._triangle_wave(n, 400) * 255)
        return (r, g, b)

    def _triangle_wave(self, x, period):
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
        # TODO Parse, don't eval. But for now it must work with the mpc type.
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

def arbitrary_precision_handler(viewport, tk_boolvar):
    viewport.set_arbitrary_precision(tk_boolvar.get())

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
    viewport = Viewport(embed.winfo_id(), dimensions=widget_size(embed))

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
    menu_arbitrary_precision = tk.BooleanVar()
    menu_arbitrary_precision.set(DEFAULT_ARBITRARY_PRECISION)
    view_menu.add_checkbutton(label='High precision',
                              variable=menu_arbitrary_precision,
                              command=functools.partial(arbitrary_precision_handler,
                                                        viewport,
                                                        menu_arbitrary_precision))

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
    embed.bind('<Configure>', lambda _: viewport.set_dimensions(widget_size(embed)))
    embed.bind('<Visibility>', lambda _: embed.after(1, viewport.refresh))
    root.protocol('WM_DELETE_WINDOW', root.quit)

    root.mainloop()

    viewport.close()
