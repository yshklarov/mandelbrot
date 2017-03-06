import functools

import mandelbrot


def colors_of(chunk, iterations=100):
    (x, y_range, res, ims) = chunk
    results = []
    for y in y_range:
        results.append((x, y, mandelbrot.point_color(res[x] + ims[y], iterations)))
    return results

def worker(iterations):
    return functools.partial(colors_of, iterations=iterations)
