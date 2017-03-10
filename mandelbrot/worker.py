import functools

import mandelbrot

def set_arbitrary_precision(arbitrary_precision=True):
    global iterations_to_escape
    if arbitrary_precision:
        iterations_to_escape = mandelbrot.iterations_to_escape_ap
    else:
        iterations_to_escape = mandelbrot.iterations_to_escape

set_arbitrary_precision(True)

def process_chunk(chunk, max_iterations=100):
    (x, y_range, res, ims, pitch) = chunk
    results = []
    for y in y_range:
        results.append((x,
                        y,
                        iterations_to_escape(res[x] + ims[y], max_iterations),
                        pitch))
    return results

def worker(iterations):
    return functools.partial(process_chunk, max_iterations=iterations)
