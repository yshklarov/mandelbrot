import functools

import mandelbrot

def _process_chunk(chunk, function, **args):
    (x, y_range, res, ims, pitch) = chunk
    results = []
    for y in y_range:
        results.append((x,
                        y,
                        function(res[x] + ims[y], **args),
                        pitch))
    return results

def worker(max_iterations, arbitrary_precision):
    if arbitrary_precision:
        function = mandelbrot.iterations_to_escape_ap
    else:
        function = mandelbrot.iterations_to_escape
    return functools.partial(_process_chunk, function=function, max_iterations=max_iterations)
