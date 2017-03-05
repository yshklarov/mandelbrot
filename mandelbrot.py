#!/usr/bin/env python3

import tkinter as tk
import pygame
import os
import sys
import threading
import math

PROGRAM_NAME = "Mandelbrot"
WINDOW_WIDTH = 400
WINDOW_HEIGHT = 418
MAX_ITERATIONS = 600


class Viewport:    

    # Before calling, SDL_WINDOWID must be set and the window must exist.
    def __init__(self):
        self.canvas = pygame.display.set_mode()
        pygame.display.init()

        self.width, self.height = 0, 0
        self.re_min, self.re_max = -2, 0.8
        self.im_min, self.im_max = -1.4, 1.4

        self.render_sem = threading.BoundedSemaphore(1)
        self.render_sem.acquire()
        self.rendering_sem = threading.BoundedSemaphore(1)
        self.rendering_sem.acquire()
        self.redraw_sem = threading.Semaphore(1)
        self.redraw_waiting = False

        self.status_callbacks = []

        rt = threading.Thread(target=self.render)
        rt.daemon = True  # TODO: a more graceful exit
        rt.start()

    def set_size(self, width, height):
        if (self.width, self.height) != (width, height):
            self.width = width
            self.height = height
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
            y = self.width // 2

        # Center of dilation
        center_re = self.re_min + (x / self.width) * (self.re_max - self.re_min)
        center_im = self.im_min + ((self.height - y) / self.height) * (self.im_max - self.im_min)

        self.re_min = center_re - ratio*(center_re - self.re_min)
        self.re_max = center_re + ratio*(self.re_max - center_re)
        self.im_min = center_im - ratio*(center_im - self.im_min)
        self.im_max = center_im + ratio*(self.im_max - center_im)
        self.update_status()
        self.redraw()
        
    # Redraw after the given delay (in seconds). Repeat calls will reset the delay. Do not block.
    def redraw_delayed(self, delay):
        def wait():
            # Wait for timeout
            while self.redraw_sem.acquire(timeout=delay):
                pass
            self.redraw_waiting = False
            self.redraw()
        self.redraw_sem.release()
        if not self.redraw_waiting:
            self.redraw_waiting = True
            t = threading.Thread(target=wait)
            t.daemon = True
            t.start()

    # Re-render immediately. Block until rendering has begun anew.
    def redraw(self):
        self.stop = True
        self.render_sem.release()
        self.rendering_sem.acquire()
    
    def render(self):
        while True:
            self.render_sem.acquire()
            self.stop = False
            self.rendering_sem.release()
            self.canvas.fill((0, 0, 0), pygame.Rect(0, 0, self.width, self.height))
            for x in range(0, self.width):
                if self.stop:
                    break
                re = self.re_min + ( (self.re_max - self.re_min) * x / self.width )
                for y in range(0, self.height):
                    im = self.im_max - ( (self.im_max - self.im_min) * y / self.height )
                    self.canvas.set_at((x, y), mandelbrot_color(re + im*1j))
                pygame.display.update()


def widget_size(widget):
    return (widget.winfo_width(), widget.winfo_height())

# The below math stuff should be in a separate mandelbrot.py; this should be main.py

def mandelbrot_color(c):
    z = 0
    for iter in range(0, MAX_ITERATIONS):
        z = z**2 + c
        if abs(z) >= 2:
            # c is outside of set
            red   = math.floor(triangle(iter,  30) * 255)
            green = math.floor(triangle(iter, 100) * 255)
            blue  = math.floor(triangle(iter, 300) * 255)
            return (red, green, blue)
    return (0,0,0) # c might be inside the set

# Triangle wave with range from 0 to 1 and given period
def triangle(x, period):
    return 2 * abs(x/period - round(x/period))
    

if __name__ == "__main__":
    root = tk.Tk()
    root.title(PROGRAM_NAME)
    root.geometry('{}x{}'.format(WINDOW_WIDTH, WINDOW_HEIGHT))
    
    menu_bar = tk.Menu(root)
    file_menu = tk.Menu(menu_bar, tearoff=0)
    view_menu = tk.Menu(menu_bar, tearoff=0)
    help_menu = tk.Menu(menu_bar, tearoff=0)
    menu_bar.add_cascade(label='File', menu=file_menu)
    menu_bar.add_cascade(label='View', menu=view_menu)
    #menu_bar.add_cascade(label='Help', menu=help_menu)
    file_menu.add_command(label='Quit', accelerator='q', command=root.destroy)
    #help_menu.add_command(label='Guide')
    #help_menu.add_command(label='About')
    root.config(menu=menu_bar)
    
    embed = tk.Frame(root)
    embed.pack(expand=1, fill=tk.BOTH)

    status = tk.StringVar()
    status_bar = tk.Label(root, bd=1, relief=tk.SUNKEN, anchor=tk.W, height=1, textvariable=status)
    status_bar.pack(fill=tk.X)

    os.environ['SDL_WINDOWID'] = str(embed.winfo_id())
    root.update()  # Initialize window before creating viewport

    viewport = Viewport()
    viewport.register_status_callback(status.set)
    viewport.set_size(*widget_size(embed))
    
    root.bind_all('q', lambda _: root.destroy())
    root.bind_all('r', lambda _: viewport.redraw())
    root.bind_all('<Key-F1>', lambda _: status.set('Drag to move; scroll to zoom'))

    view_menu.add_command(label='Zoom In', accelerator='+', command=viewport.zoom_in)
    view_menu.add_command(label='Zoom Out', accelerator='-', command=viewport.zoom_out)
    embed.bind('<Button-4>', lambda ev: viewport.zoom_in(x=ev.x, y=ev.y))
    root.bind('<KP_Add>', lambda _: viewport.zoom_in())
    embed.bind('<Button-5>', lambda ev: viewport.zoom_out(x=ev.x, y=ev.y))
    root.bind('<KP_Subtract>', lambda _: viewport.zoom_out())

    # Window resize or move
    root.bind('<Configure>', lambda _: viewport.set_size(*widget_size(embed)))

    root.mainloop()
