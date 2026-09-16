"""Cairo character artwork shared by the native window and preview renderer."""
import math
import cairo
IDLE, THINK, TALK, ALERT = 0, 1, 2, 3


def rounded(cr, x, y, w, h, r):
    cr.new_sub_path()
    for cx, cy, start in [(x+w-r, y+r, -math.pi/2), (x+w-r, y+h-r, 0),
                          (x+r, y+h-r, math.pi/2), (x+r, y+r, math.pi)]:
        cr.arc(cx, cy, r, start, start+math.pi/2)
    cr.close_path()


def draw_friend(cr, width, height, t, mood=IDLE):
    cr.save(); cr.scale(width/160, height/180)
    cr.set_operator(cairo.OPERATOR_SOURCE); cr.set_source_rgba(0, 0, 0, 0); cr.paint()
    cr.set_operator(cairo.OPERATOR_OVER)
    colors = {IDLE:(0.22,0.93,0.66), THINK:(0.3,0.78,1), TALK:(0.22,0.93,0.66), ALERT:(1,0.67,0.23)}
    color = colors[mood]
    hover = math.sin(t*2.1)*3
    glow = cairo.RadialGradient(80, 92, 20, 80, 92, 76)
    glow.add_color_stop_rgba(0, *color, .18); glow.add_color_stop_rgba(1, *color, 0)
    cr.set_source(glow); cr.paint()
    cr.save(); cr.translate(80, 157); cr.scale(1,.22)
    cr.set_source_rgba(*color,.20); cr.arc(0,0,40,0,math.tau); cr.fill(); cr.restore()
    cr.translate(0,hover)
    # Body and floating boots.
    for x in (54,87):
        rounded(cr,x,136,20,10,5); cr.set_source_rgba(.06,.14,.17,1); cr.fill()
        cr.set_source_rgba(*color,.8); cr.rectangle(x+4,145,12,2); cr.fill()
    shell = cairo.LinearGradient(45,80,111,135)
    shell.add_color_stop_rgb(0,.23,.34,.38); shell.add_color_stop_rgb(.4,.08,.16,.2)
    shell.add_color_stop_rgb(1,.03,.08,.12)
    rounded(cr,46,95,68,46,15); cr.set_source(shell); cr.fill_preserve()
    cr.set_source_rgba(*color,.5); cr.set_line_width(1.4); cr.stroke()
    # Arms: a small greeting wave while idle, working pulse while thinking.
    for sign in (-1,1):
        cr.save(); cr.translate(80+sign*35,108)
        angle = sign*(.35+(.30*math.sin(t*3) if sign==1 and mood==IDLE else .1*math.sin(t*4)))
        cr.rotate(angle)
        rounded(cr,-7,0,14,26,6); cr.set_source_rgb(.10,.22,.26); cr.fill_preserve()
        cr.set_source_rgba(*color,.55); cr.stroke(); cr.restore()
    # Antenna.
    cr.set_line_width(3); cr.set_source_rgb(.18,.34,.37)
    cr.move_to(80,36); cr.line_to(80,25); cr.stroke()
    cr.set_source_rgba(*color,.8+.2*math.sin(t*3)); cr.arc(80,23,4,0,math.tau); cr.fill()
    rounded(cr,35,37,90,65,22); cr.set_source(shell); cr.fill_preserve()
    cr.set_source_rgba(*color,.8); cr.set_line_width(1.8); cr.stroke()
    rounded(cr,42,45,76,44,15); cr.set_source_rgb(.012,.04,.055); cr.fill()
    # Glass highlight.
    rounded(cr,47,49,60,4,2); cr.set_source_rgba(.7,.95,1,.12); cr.fill()
    blink = max(.07, 1-max(0, math.cos(t*1.25))**44)
    gaze = math.sin(t*.7)*2
    cr.set_source_rgb(*color)
    for x in (62,96):
        h = 2+12*blink
        rounded(cr,x-5+gaze,64-h/2,10,h,min(4,h/2)); cr.fill()
    cr.set_line_width(2.4); cr.set_line_cap(cairo.LINE_CAP_ROUND)
    if mood==ALERT:
        cr.move_to(75,80);cr.line_to(85,80);cr.stroke()
    else:
        cr.move_to(73,79)
        cr.curve_to(76,84+(3*abs(math.sin(t*9)) if mood==TALK else 0),84,84,87,79)
        cr.stroke()
    # Chest core and status lights.
    cr.set_source_rgba(*color,.2);cr.arc(80,117,12,0,math.tau);cr.fill()
    cr.set_source_rgb(*color);cr.arc(80,117,5+math.sin(t*(5 if mood==THINK else 2)),0,math.tau);cr.fill()
    for i in range(3):
        cr.set_source_rgba(*color,.3+.6*(.5+.5*math.sin(t*4-i)))
        rounded(cr,68+i*9,132,5,2,1);cr.fill()
    if mood==THINK:
        for i in range(3):
            cr.set_source_rgba(*color,.35+.6*(.5+.5*math.sin(t*5-i)))
            cr.arc(67+i*13,12,2.5,0,math.tau);cr.fill()
    cr.restore()
