import math

from mpmath import mp


ESCAPE_RADIUS = 10**100
ESCAPE_MAGNITUDE = math.log2(ESCAPE_RADIUS)

# Decimal places of precision. The default is 15, corresponding to standard double precision (53
# binary digits. To be able to use 10^k times zoom, set this to at least k + 4.
mp.dps = 54


# TODO Speed up this function. It is the bottleneck by a long shot.
def iterations_to_escape_ap(c, max_iterations=100):
    """ Calculate the number of iterations to escape the mandelbrot set.

    Uses arbitrary precision for calculations. Returns an (interpolated)
    mpmath floating point value. If no escape, returns a value greater
    than max_iterations.
    """
    iterations = 0
    z = mp.mpc(0)
    while mp.mag(z) < ESCAPE_MAGNITUDE:
        iterations += 1
        if iterations > max_iterations:
            break
        z = z*z + c
    inner_log = mp.log(mp.fabs(z) / ESCAPE_MAGNITUDE)
    if inner_log.real > 0:
        adjustment = 1 - mp.log(inner_log, b=2)
    else:
        adjustment = 0
    return float(iterations + adjustment)


def iterations_to_escape(c, max_iterations=100):
    """ Calculate the number of iterations to escape the mandelbrot set.

    Returns an (interpolated) floating point value. If no escape,
    returns a value greater than max_iterations.
    """
    iterations = 0
    z = 0
    while abs(z) < ESCAPE_RADIUS:
        iterations += 1
        if iterations > max_iterations:
            break
        z = z**2 + c
    try:
        adjustment = 1 - math.log2(math.log(abs(z) / ESCAPE_MAGNITUDE))
    except ValueError:
        adjustment = 0
    return iterations + adjustment
