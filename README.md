Mandelbrot
==========

This is a simple desktop tool for exploring the Mandelbrot set.

Features
--------

  * Parallel rendering
  * Arbitrary precision (quite slow: off by default)
  * Multi-pass (progressive) rendering
  * Smooth coloring

![screenshot](docs/screenshot.jpg)

Usage
-----

  * Scroll to zoom, drag to pan.
  * The maximum number of iterations can be configured from the View menu.
  * If you want to zoom beyond 1e12 times, set `ARBITRARY_PRECISION` to `True` in `mandelbrot/main.py`.

Requirements
------------

  * Python 3
  * Pygame
  * Mpmath

No installation required: simply run `mandelbrot/main.py`.