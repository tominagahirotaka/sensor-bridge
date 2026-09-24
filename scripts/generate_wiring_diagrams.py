#!/usr/bin/env python3
"""Regenerate the wiring-diagram SVGs referenced from README.md's
"Wiring diagrams" section: docs/wiring/{lis3dh,sht35,mic}.svg.

Pin assignments are hand-transcribed from the actual .ini configs and
firmware source (LIS3DH.ini's spi_*_pin defaults; SHT35.ini's i2c_pinno
plus PICO_i2cSHT35.ino's i2c_begin(), which pairs SDA=pin with
SCL=pin+1; the mic's GP26/ADC0 per Analog.ini) -- if any of those change,
re-run this script rather than hand-editing the SVGs. Diagrams label
wires by function (VCC/GND/SDA/SCL/CS/...), not by physical pin
position, so they don't depend on knowing a specific breakout board
revision's exact silkscreen layout.

Usage: python scripts/generate_wiring_diagrams.py   (from the repo root)
"""

import os

COLORS = {
    'power': '#dc2626',   # red: 3V3/VCC
    'gnd': '#374151',     # dark gray: GND
    'sig1': '#2563eb',    # blue
    'sig2': '#d97706',    # orange
    'sig3': '#059669',    # green
    'sig4': '#7c3aed',    # purple
    'muted': '#9ca3af',
}

FONT = 'font-family="Helvetica, Arial, sans-serif"'


def box(x, y, w, h, title):
    return '\n'.join([
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" '
        f'fill="#f8fafc" stroke="#1f2937" stroke-width="2"/>',
        f'<text x="{x + w / 2}" y="{y + 24}" text-anchor="middle" {FONT} '
        f'font-size="15" font-weight="bold" fill="#111827">{title}</text>',
    ])


def text_bg(x, y, text, anchor, size=12.5, weight='normal'):
    """A label with an opaque background rect behind it, so a wire/line
    passing under the label is visually occluded rather than crossing
    through the text."""
    approx_w = len(text) * size * 0.62
    if anchor == 'start':
        rx = x - 3
    elif anchor == 'end':
        rx = x - approx_w - 3
    else:
        rx = x - approx_w / 2 - 3
    return '\n'.join([
        f'<rect x="{rx:.1f}" y="{y - size:.1f}" width="{approx_w + 6:.1f}" '
        f'height="{size + 6:.1f}" fill="#ffffff"/>',
        f'<text x="{x}" y="{y + 4}" text-anchor="{anchor}" {FONT} '
        f'font-size="{size}" font-weight="{weight}" fill="#111827">{text}</text>',
    ])


def pin_stub(x, y, label, side, color, length=26, label_gap=10):
    """A short stub line + dot at (x,y) extending toward `side`
    ('right'/'left'), with a label placed just past the dot, clear of the
    stub itself. Returns (svg_fragment, endpoint_x)."""
    if side == 'right':
        x2 = x + length
        anchor, lx = 'start', x2 + label_gap
    else:
        x2 = x - length
        anchor, lx = 'end', x2 - label_gap
    parts = [
        f'<line x1="{x}" y1="{y}" x2="{x2}" y2="{y}" stroke="{color}" stroke-width="3"/>',
        f'<circle cx="{x2}" cy="{y}" r="3.5" fill="{color}"/>',
        text_bg(lx, y, label, anchor),
    ]
    return '\n'.join(parts), x2


def wire(x1, y1, x2, y2, color):
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{color}" stroke-width="3"/>')


def svg_header(w, h, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{title}">\n'
            f'<rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff"/>')


def svg_footer():
    return '</svg>'


def legend(x, y, entries):
    parts = []
    for i, (color, text) in enumerate(entries):
        yy = y + i * 20
        parts.append(f'<line x1="{x}" y1="{yy}" x2="{x + 22}" y2="{yy}" '
                     f'stroke="{color}" stroke-width="4"/>')
        parts.append(f'<text x="{x + 30}" y="{yy + 4}" {FONT} font-size="12" '
                     f'fill="#374151">{text}</text>')
    return '\n'.join(parts)


def caption(w, y, text):
    return (f'<text x="{w/2}" y="{y}" text-anchor="middle" {FONT} '
           f'font-size="11" fill="#6b7280">{text}</text>')


# ---------------------------------------------------------------------
# A simple "Pico <-> single device, N labeled pin pairs" layout, shared
# by the LIS3DH and mic diagrams.
# ---------------------------------------------------------------------
def two_box_diagram(w, h, title, dev_title, rows, row_top, row_gap,
                    pico_box, dev_box, footnote):
    svg = [svg_header(w, h, title)]
    svg.append(box(*pico_box, 'Raspberry Pi Pico'))
    svg.append(box(*dev_box, dev_title))
    pico_x, _, pico_w, _ = pico_box
    dev_x = dev_box[0]
    for i, (pico_label, dev_label, color) in enumerate(rows):
        y = row_top + i * row_gap
        stub_l, x_l = pin_stub(pico_x + pico_w, y, pico_label, 'right', color)
        stub_r, x_r = pin_stub(dev_x, y, dev_label, 'left', color)
        svg.append(wire(x_l, y, x_r, y, color))  # draw wire first, labels/bg on top
        svg.append(stub_l)
        svg.append(stub_r)
    svg.append(legend(40, h - 46, [
        (COLORS['power'], 'power (3.3V)'),
        (COLORS['gnd'], 'ground'),
    ]))
    svg.append(caption(w, h - 10, footnote))
    svg.append(svg_footer())
    return '\n'.join(svg)


def make_lis3dh():
    rows = [
        ('3V3', 'VCC', COLORS['power']),
        ('GND', 'GND', COLORS['gnd']),
        ('GP17', 'CS', COLORS['sig1']),
        ('GP18', 'SCK', COLORS['sig2']),
        ('GP19', 'MOSI (SDI)', COLORS['sig3']),
        ('GP16', 'MISO (SDO)', COLORS['sig4']),
    ]
    row_top, row_gap = 90, 38
    box_bottom = row_top + (len(rows) - 1) * row_gap + 40
    W, H = 680, box_bottom + 70
    return two_box_diagram(
        W, H, 'Pico to LIS3DH SPI wiring diagram', 'LIS3DH (SPI accelerometer)',
        rows, row_top, row_gap,
        pico_box=(40, 40, 170, box_bottom - 20),
        dev_box=(470, 55, 170, box_bottom - 45),
        footnote='SPI0 default pins (SCK/MOSI/MISO fixed at GP18/19/16); '
                'CS is configurable via spi_cs_pin in LIS3DH.ini')


def make_mic():
    rows = [
        ('3V3', 'VCC', COLORS['power']),
        ('GND', 'GND', COLORS['gnd']),
        ('GP26 (ADC0)', 'OUT', COLORS['sig1']),
    ]
    row_top, row_gap = 90, 38
    box_bottom = row_top + (len(rows) - 1) * row_gap + 40
    W, H = 620, box_bottom + 70
    return two_box_diagram(
        W, H, 'Pico to AE-MICAMP microphone wiring diagram', 'Akizuki AE-MICAMP',
        rows, row_top, row_gap,
        pico_box=(40, 40, 170, box_bottom - 20),
        dev_box=(410, 55, 170, box_bottom - 45),
        footnote='JP1 on the module: pin1=VCC, pin2=GND, pin3=OUT -- '
                'no extra components needed')


# ---------------------------------------------------------------------
# SHT35: 2 I2C buses, 2 sensors each (address-multiplexed) = 4 sensors
# ---------------------------------------------------------------------
def sensor_box(x, y, w, h, title, addr, addr_pin):
    parts = [box(x, y, w, h, title)]
    rows = [('SDA', COLORS['sig1']), ('SCL', COLORS['sig2']),
           ('VDD', COLORS['power']), ('GND', COLORS['gnd']),
           (f'ADDR → {addr_pin}  (addr {addr})', COLORS['muted'])]
    for i, (label, color) in enumerate(rows):
        yy = y + 42 + i * 16
        parts.append(f'<circle cx="{x + 14}" cy="{yy - 4}" r="3" fill="{color}"/>')
        parts.append(f'<text x="{x + 24}" y="{yy}" {FONT} font-size="11.5" '
                     f'fill="#111827">{label}</text>')
    return '\n'.join(parts), (x, y + 50), (x, y + 66)  # box, sda-in-pt, scl-in-pt


def bus_block(pico_x, pico_w, bus_label, box_top, sda_pico, scl_pico,
             sensor_xs, sensor_w, sensor_h):
    """One I2C bus: SDA/SCL pins on the Pico (vertically aligned with the
    sensor boxes' own SDA/SCL rows), a shared trunk, and 2 sensor boxes
    branching off it side by side. box_top is the sensor boxes' top y."""
    sda_y = box_top + 42   # matches sensor_box()'s internal SDA row
    scl_y = box_top + 58   # matches sensor_box()'s internal SCL row
    title_y = box_top - 14

    parts = [text_bg(pico_x + pico_w + 40, title_y, bus_label, 'start',
                     size=13, weight='bold')]
    trunk_x = pico_x + pico_w + 66
    pins = [(sda_pico, 'SDA', COLORS['sig1'], sda_y),
           (scl_pico, 'SCL', COLORS['sig2'], scl_y)]
    for pico_label, sig, color, y in pins:
        stub, x_end = pin_stub(pico_x + pico_w, y, pico_label, 'right', color, length=18)
        parts.append(wire(x_end, y, trunk_x, y, color))
        parts.append(stub)
    for sx in sensor_xs:
        parts.append(wire(trunk_x, sda_y, sx, sda_y, COLORS['sig1']))
        parts.append(wire(trunk_x, scl_y, sx, scl_y, COLORS['sig2']))
    return '\n'.join(parts)


def make_sht35():
    sensor_w, sensor_h = 190, 112
    sx1, sx2 = 420, 660
    box_top_A, box_top_B = 140, 360
    W = sx2 + sensor_w + 40

    pico_x, pico_w, pico_y = 40, 170, 40
    last_sensor_bottom = box_top_B + sensor_h
    pico_h = last_sensor_bottom - pico_y  # bottom edges aligned with the sensor boxes
    legend_y = max(last_sensor_bottom, pico_y + pico_h) + 30
    H = legend_y + 4 * 20 + 30

    svg = [svg_header(W, H, 'Pico to 4x SHT35 I2C wiring diagram (2 buses x 2 sensors)')]
    svg.append(box(pico_x, pico_y, pico_w, pico_h, 'Raspberry Pi Pico'))

    # shared power, routed down the right edge of the Pico box
    power_x = pico_x + pico_w + 24
    power_ys = {}
    for i, (label, color) in enumerate([('3V3', COLORS['power']), ('GND', COLORS['gnd'])]):
        y = pico_y + 26 + i * 24
        power_ys[label] = (power_x + i * 10, color)
        stub, x_end = pin_stub(pico_x + pico_w, y, label, 'right', color, length=14)
        svg.append(wire(x_end, y, power_x + i * 10, y, color))
        svg.append(wire(power_x + i * 10, y, power_x + i * 10, H - 76, color))
        svg.append(stub)

    svg.append(bus_block(pico_x, pico_w, 'Bus A (I2C0 / Wire)', box_top_A,
                         'GP20', 'GP21', [sx1, sx2], sensor_w, sensor_h))
    svg.append(sensor_box(sx1, box_top_A, sensor_w, sensor_h, 'SHT35 #1', '0x44', 'GND')[0])
    svg.append(sensor_box(sx2, box_top_A, sensor_w, sensor_h, 'SHT35 #2', '0x45', 'VDD')[0])

    svg.append(bus_block(pico_x, pico_w, 'Bus B (I2C1 / Wire1)', box_top_B,
                         'GP18', 'GP19', [sx1, sx2], sensor_w, sensor_h))
    svg.append(sensor_box(sx1, box_top_B, sensor_w, sensor_h, 'SHT35 #3', '0x44', 'GND')[0])
    svg.append(sensor_box(sx2, box_top_B, sensor_w, sensor_h, 'SHT35 #4', '0x45', 'VDD')[0])

    # power/gnd wires into each sensor box (from the shared vertical rails)
    for box_top in (box_top_A, box_top_B):
        for sx in (sx1, sx2):
            vdd_y, gnd_y = box_top + 74, box_top + 90
            px, pcolor = power_ys['3V3']
            gx, gcolor = power_ys['GND']
            svg.append(wire(px, vdd_y, sx, vdd_y, pcolor))
            svg.append(wire(gx, gnd_y, sx, gnd_y, gcolor))

    svg.append(legend(40, legend_y, [
        (COLORS['power'], 'power (3.3V, shared)'),
        (COLORS['gnd'], 'ground (shared)'),
        (COLORS['sig1'], 'SDA'),
        (COLORS['sig2'], 'SCL'),
    ]))
    svg.append(caption(W, H - 12,
                       'Each bus carries 2 sensors at different I2C addresses '
                       '(ADDR pin to GND = 0x44, to VDD = 0x45)'))
    svg.append(svg_footer())
    return '\n'.join(svg)


# ---------------------------------------------------------------------
# DPG_X95840W_LIS3DHx2: Pico + the X95840W PPG front end + 2x LIS3DH
# sharing SPI0 (CS moved off GP17, which X95840W uses, to GP22/GP2).
#
# UNLIKE the other three diagrams, this one is NOT transcribed from a
# known breakout board's silkscreen -- the X95840W front end is a
# bespoke circuit with no schematic in this repository (see the paper's
# Illustrative examples section), and the combined circuit itself has
# never been physically built (see docs/adding-a-board.md and
# README.md's hardware-verification matrix: DPG_X95840W_LIS3DHx2 is
# "compiled, not yet hardware-tested" on every board). Every pin shown
# here is a verified GPIO assignment from DPG_X95840W_LIS3DHx2.ini and
# PICO_DPG_X95840W_LIS3DHx2.ino/utils.cpp (i2c_pinno=20 -> SDA=GP20/
# SCL=GP21 by i2c_begin()'s SDA-then-SDA+1 convention; GP17 as a
# separate enable/latch pin; port_num=0,1,2 -> analogRead(indx+
# ANALOGPIN0) -> GP26/27/28; spi_cs_pin1/2=22,15 -- GP15 rather than the
# also-free GP2, since GP15/GP16 sit directly across from each other at
# the bottom edge of the Pico's physical header, the closest free pin to
# the GP16/18/19/22 cluster this circuit already uses), not a claim about the
# X95840W board's internal schematic or exact physical layout.
# ---------------------------------------------------------------------
def make_dpg_x95840w_lis3dhx2():
    x95840w_rows = [
        ('5V (VBUS)', 'VCC', COLORS['power']),
        ('GND', 'GND', COLORS['gnd']),
        ('GP17', 'ENABLE (I2C latch)', COLORS['sig1']),
        ('GP20', 'SDA', COLORS['sig2']),
        ('GP21', 'SCL', COLORS['sig3']),
        ('GP26 (ADC0)', 'PORT0', COLORS['sig4']),
        ('GP27 (ADC1)', 'PORT1', COLORS['sig1']),
        ('GP28 (ADC2)', 'PORT2', COLORS['sig2']),
    ]
    pico_x, pico_y, pico_w = 40, 40, 190
    row_top, row_gap = 90, 32
    x95840w_x = 520
    x95840w_box_h = row_top + (len(x95840w_rows) - 1) * row_gap + 40
    x95840w_box = (x95840w_x, 30, 230, x95840w_box_h - 10)

    lis3dh_w, lis3dh_h = 220, 190
    section_gap = 110
    lis3dh_y = x95840w_box[1] + x95840w_box[3] + section_gap
    lis3dh_x1, lis3dh_x2 = 420, 700

    # 5 shared signals routed from the Pico (power + SPI0), aligned so
    # each wire's y exactly matches the corresponding internal row's dot
    # in the LIS3DH boxes below (see the "- 4" in that loop).
    shared_signals = [
        ('3V3', 'VCC', COLORS['power']),
        ('GND', 'GND', COLORS['gnd']),
        ('GP18', 'SCK', COLORS['sig2']),
        ('GP19', 'SDI (MOSI)', COLORS['sig3']),
        ('GP16', 'SDO (MISO)', COLORS['sig4']),
    ]
    spi_row_top, spi_row_gap = lis3dh_y + 30, 20

    pico_h = lis3dh_y + lis3dh_h - pico_y
    W = lis3dh_x2 + lis3dh_w + 40
    H = lis3dh_y + lis3dh_h + 90

    svg = [svg_header(W, H, 'Pico to X95840W + 2x LIS3DH wiring diagram '
                            '(untested combined circuit)')]
    svg.append(box(pico_x, pico_y, pico_w, pico_h, 'Raspberry Pi Pico'))
    svg.append(box(*x95840w_box, 'X95840W PPG front end (bespoke, no schematic)'))

    for i, (pico_label, dev_label, color) in enumerate(x95840w_rows):
        y = row_top + i * row_gap
        stub_l, x_l = pin_stub(pico_x + pico_w, y, pico_label, 'right', color)
        stub_r, x_r = pin_stub(x95840w_box[0], y, dev_label, 'left', color)
        svg.append(wire(x_l, y, x_r, y, color))
        svg.append(stub_l)
        svg.append(stub_r)

    # LIS3DH x2, sharing power + SPI0 (SCK/MOSI/MISO). CS is per-device
    # (GP22 for #1, GP2 for #2) and shown as a label inside each box,
    # the same way the SHT35 diagram shows each sensor's ADDR strap,
    # rather than as a wire drawn all the way from the Pico -- with two
    # side-by-side target boxes, a genuinely per-device signal would
    # otherwise have to visually cross the shared-bus trunk.
    svg.append(text_bg(pico_x + pico_w + 40, lis3dh_y - 14,
                       'SPI0 (shared bus)', 'start', size=13, weight='bold'))
    trunk_x = pico_x + pico_w + 70
    for i, (pico_label, sig, color) in enumerate(shared_signals):
        y = spi_row_top + i * spi_row_gap
        stub, x_end = pin_stub(pico_x + pico_w, y, pico_label, 'right', color, length=18)
        svg.append(wire(x_end, y, trunk_x, y, color))
        svg.append(stub)
        for lx in (lis3dh_x1, lis3dh_x2):
            svg.append(wire(trunk_x, y, lx, y, color))

    for lx, cs_pin, title in ((lis3dh_x1, 'GP22', 'LIS3DH #1'),
                              (lis3dh_x2, 'GP15', 'LIS3DH #2')):
        svg.append(box(lx, lis3dh_y, lis3dh_w, lis3dh_h, title))
        rows_local = [('VCC', COLORS['power']), ('GND', COLORS['gnd']),
                     ('SCK', COLORS['sig2']), ('SDI', COLORS['sig3']),
                     ('SDO', COLORS['sig4']),
                     (f'CS ← {cs_pin} (not shared)', COLORS['muted'])]
        for i, (label, color) in enumerate(rows_local):
            yy = lis3dh_y + 34 + i * 20
            svg.append(f'<circle cx="{lx + 14}" cy="{yy - 4}" r="3" fill="{color}"/>')
            svg.append(f'<text x="{lx + 24}" y="{yy}" {FONT} font-size="11.5" '
                       f'fill="#111827">{label}</text>')

    svg.append(legend(40, H - 46, [
        (COLORS['power'], 'power'),
        (COLORS['gnd'], 'ground'),
    ]))
    svg.append(caption(W, H - 10,
                       'GPIO assignments verified from .ini/firmware source only -- '
                       'circuit not yet physically built (see README.md)'))
    svg.append(svg_footer())
    return '\n'.join(svg)


if __name__ == '__main__':
    out_dir = 'docs/wiring'
    os.makedirs(out_dir, exist_ok=True)
    with open(f'{out_dir}/lis3dh.svg', 'w') as f:
        f.write(make_lis3dh())
    with open(f'{out_dir}/mic.svg', 'w') as f:
        f.write(make_mic())
    with open(f'{out_dir}/sht35.svg', 'w') as f:
        f.write(make_sht35())
    with open(f'{out_dir}/dpg_x95840w_lis3dhx2.svg', 'w') as f:
        f.write(make_dpg_x95840w_lis3dhx2())
    print('wrote', out_dir)
