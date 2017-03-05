import math

def point_color(c, iterations=100):
    z = 0
    for iter in range(0, iterations):
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
