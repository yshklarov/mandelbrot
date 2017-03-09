def iterations_to_escape(c, max_iterations=100):
    """ If no escape, returns max_iterations + 1. """
    iterations = 0
    z = 0
    while abs(z) < 2:
        iterations += 1
        if iterations > max_iterations:
            break
        z = z**2 + c
    return iterations
