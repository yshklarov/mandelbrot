import math

ESCAPE_RADIUS = 10**100

def iterations_to_escape(c, max_iterations=100):
    """ If no escape, returns max_iterations + 1. """
    iterations = 0
    z = 0
    while abs(z) < ESCAPE_RADIUS:
        iterations += 1
        if iterations > max_iterations:
            break
        z = z**2 + c
    try:
        adjustment = 1 - math.log2(math.log(abs(z))/math.log(ESCAPE_RADIUS))
    except ValueError:
        adjustment = 0
    return iterations + adjustment
