import functools

import mandelbrot


def process_chunk(chunk, max_iterations=100):
    (x, y_range, res, ims, pitch) = chunk
    results = []
    for y in y_range:
        results.append((x,
                        y,
                        mandelbrot.iterations_to_escape(res[x] + ims[y], max_iterations),
                        pitch))
    return results

def worker(iterations):
    return functools.partial(process_chunk, max_iterations=iterations)
