#!/usr/bin/env python3

import tkinter as tk
import pygame
import os
import sys
import multiprocessing as mp
import queue
import threading

import mandelbrot

PROGRAM_NAME = "Mandelbrot"
WINDOW_WIDTH = 400
WINDOW_HEIGHT = 418
MAX_ITERATIONS = 600


class Viewport:    

    # The window referenced by window_id must exist (eg. call root.update() in tkinter)
    def __init__(self, window_id):
        self.width, self.height = 0, 0
        self.re_min, self.re_max = -2, 0.8
        self.im_min, self.im_max = -1.4, 1.4

        self.redraw_sem = mp.Semaphore()
        self.redraw_waiting = False

        self.render_event = mp.Event()
        self.refresh_event = mp.Event()
        self.stop_event = mp.Event()
        self.quit_event = mp.Event()
        self.size_q = mp.Queue()
        self.bounds_q = mp.Queue()

        self.status_callbacks = []

        self.render_p = mp.Process(target=self.render, daemon=True, args=[window_id])
        self.render_p.start()

    def set_size(self, width, height):
        if (self.width, self.height) != (width, height):
            self.width = width
            self.height = height
            self.size_q.put((self.width, self.height))
            self.redraw_delayed(0.100)
        self.update_status()

    def register_status_callback(self, cb):
        self.status_callbacks.append(cb)

    def update_status(self):
        for cb in self.status_callbacks:
            cb(self.status_string())

    def status_string(self):
        zoom = 4 / max(self.re_max - self.re_min,
                       self.im_max - self.im_min)
        return '{:.6f} + {:.6f}i; Zoom = {:.3g}; {}x{}'.format(
            (self.re_min + self.re_max) / 2, (self.im_min + self.im_max) / 2,
            zoom, self.width, self.height)

    def zoom_in(self, x=None, y=None):
        self.dilate(0.5, x, y)

    def zoom_out(self, x=None, y=None):
        self.dilate(2, x, y)
    
    def dilate(self, ratio, x=None, y=None):
        if x is None:
            x = self.width // 2
        if y is None:
            y = self.height // 2

        # Center of dilation
        center_re = self.re_min + (x / self.width) * (self.re_max - self.re_min)
        center_im = self.im_min + ((self.height - y) / self.height) * (self.im_max - self.im_min)

        self.re_min = center_re - ratio*(center_re - self.re_min)
        self.re_max = center_re + ratio*(self.re_max - center_re)
        self.im_min = center_im - ratio*(center_im - self.im_min)
        self.im_max = center_im + ratio*(self.im_max - center_im)

        self.bounds_q.put((self.re_min, self.re_max, self.im_min, self.im_max))
        self.update_status()
        self.redraw()

    # Re-paint the window surface (without rendering anew)
    def refresh(self):
        self.refresh_event.set()

    def refresh_watchdog(self):
        while self.refresh_event.wait():
            self.refresh_event.clear()
            pygame.display.update()

    def close(self):
        self.quit_event.set()
        self.stop_event.set()
        self.render_event.set()  # Release block in render()

    # Call redraw() after the given delay (in seconds). Repeat calls will reset the delay. Do not block.
    def redraw_delayed(self, delay):
        if not self.redraw_waiting:
            def wait():
                # Wait until 'delay' seconds after the last acquire
                while self.redraw_sem.acquire(timeout=delay):
                    pass
                self.redraw_waiting = False
                self.redraw()
            self.redraw_waiting = True
            t = threading.Thread(target=wait, daemon=True)
            t.start()
        self.redraw_sem.release()

    # Re-render immediately. Block until rendering has begun anew.
    def redraw(self):
        self.stop_event.set()
        self.render_event.set()

    def render(self, window_id):
        os.environ['SDL_WINDOWID'] = str(window_id)
        self.canvas = pygame.display.set_mode()
        pygame.display.init()
        threading.Thread(target=self.refresh_watchdog, daemon=True).start()

        while not self.quit_event.is_set():
            self.render_event.wait()
            self.render_event.clear()
            self.stop_event.clear()

            # Get new size if changed
            try:
                while True:
                    self.width, self.height = self.size_q.get_nowait()
            except queue.Empty as e: pass

            # Get new bounds if changed
            try:
                while True:
                    self.re_min, self.re_max, self.im_min, self.im_max = \
                            self.bounds_q.get_nowait()
            except queue.Empty as e: pass

            self.canvas.fill((0, 0, 0), pygame.Rect(0, 0, self.width, self.height))

            for x in range(0, self.width):
                if self.stop_event.is_set() or self.quit_event.is_set():
                    break
                re = self.re_min + ( (self.re_max - self.re_min) * x / self.width )
                for y in range(0, self.height):
                    im = self.im_max - ( (self.im_max - self.im_min) * y / self.height )
                    self.canvas.set_at((x, y), mandelbrot.point_color(
                        re + im*1j, MAX_ITERATIONS))
                pygame.display.update()


def widget_size(widget):
    return (widget.winfo_width(), widget.winfo_height())


if __name__ == "__main__":
    mp.set_start_method('spawn')

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
    status_bar = tk.Label(root, bd=1, relief=tk.SUNKEN, anchor=tk.W, height=1, textvariable=status)
    status_bar.pack(fill=tk.X)

    file_menu = tk.Menu(menu_bar, tearoff=0)
    view_menu = tk.Menu(menu_bar, tearoff=0)
    help_menu = tk.Menu(menu_bar, tearoff=0)
    menu_bar.add_cascade(label='File', menu=file_menu)
    menu_bar.add_cascade(label='View', menu=view_menu)
    #menu_bar.add_cascade(label='Help', menu=help_menu)
    file_menu.add_command(label='Quit', accelerator='q', command=root.quit)
    view_menu.add_command(label='Redraw', accelerator='r', command=viewport.redraw)
    view_menu.insert_separator(1)
    view_menu.add_command(label='Zoom In', accelerator='+', command=viewport.zoom_in)
    view_menu.add_command(label='Zoom Out', accelerator='-', command=viewport.zoom_out)
    #help_menu.add_command(label='Guide')
    #help_menu.add_command(label='About')

    root.bind_all('q', lambda _: root.quit())
    root.bind_all('r', lambda _: viewport.redraw())
    root.bind_all('<Key-F1>', lambda _: status.set('Drag to move; scroll to zoom'))
    root.bind_all('<KP_Add>', lambda _: viewport.zoom_in())
    root.bind_all('<plus>', lambda _: viewport.zoom_in())
    root.bind_all('<KP_Subtract>', lambda _: viewport.zoom_out())
    root.bind_all('<minus>', lambda _: viewport.zoom_out())
    embed.bind('<Button-4>', lambda ev: viewport.zoom_in(x=ev.x, y=ev.y))
    embed.bind('<Button-5>', lambda ev: viewport.zoom_out(x=ev.x, y=ev.y))

    # <Configure> gets called on widget resize
    embed.bind('<Configure>', lambda _: viewport.set_size(*widget_size(embed)))
    embed.bind('<Visibility>', lambda _: embed.after(1, viewport.refresh))

    viewport.set_size(*widget_size(embed))
    viewport.register_status_callback(status.set)

    root.mainloop()

    viewport.close()
