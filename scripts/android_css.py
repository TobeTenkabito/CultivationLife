"""Compile sRGB color-mix to equivalent channel expressions for Android 12 WebView 91.

Channel variables follow the same cascade as their color variables, including DLC
and HP/MP accents. No theme is flattened into another theme's palette.
"""
import re

COLOR = r'(?:var\(--[\w-]+\)|\#[0-9a-fA-F]{3,8}|transparent|white|black|rgba?\([^()]+\))'
MIX = re.compile(r'color-mix\(\s*in srgb\s*,\s*('+COLOR+r')\s*([\d.]+)%\s*,\s*('+COLOR+r')\s*\)')
DECL = re.compile(r'(--[\w-]+)\s*:\s*([^;{}]+)(?=[;}])')


def channels(color):
    color = color.strip()
    if color.startswith('var('):
        name = color[4:-1]
        return tuple(f'var({name}-{c})' for c in 'rgba')
    if color == 'transparent': return ('0','0','0','0')
    if color in ('white','black'): color = '#ffffff' if color == 'white' else '#000000'
    if color.startswith('#'):
        value = color[1:]
        if len(value) in (3,4): value = ''.join(c*2 for c in value)
        rgb = tuple(str(int(value[i:i+2],16)) for i in (0,2,4))
        return (*rgb, str(int(value[6:],16)/255) if len(value) == 8 else '1')
    if color.startswith('rgb'):
        values = tuple(s.strip() for s in color[color.index('(')+1:-1].split(','))
        return values if len(values) == 4 else (*values,'1')
    raise ValueError(f'Unsupported Android color: {color}')


def mixed(match):
    left, weight, right = match.groups()
    a, b = channels(left), channels(right)
    p = float(weight)/100
    q = 1-p
    if right == 'transparent':
        return (*a[:3],f'calc({a[3]} * {p:g})')
    alpha = f'({a[3]} * {p:g} + {b[3]} * {q:g})'
    rgb = tuple(f'calc(({a[i]} * {a[3]} * {p:g} + {b[i]} * {b[3]} * {q:g}) / {alpha})' for i in range(3))
    return (*rgb, f'calc{alpha}')


def compile_css(css):
    def declaration(match):
        key, value = match.groups()
        if MIX.fullmatch(value): values = mixed(MIX.fullmatch(value))
        elif re.fullmatch(COLOR, value.strip()): values = channels(value)
        else: return match.group(0)
        return match.group(0) + ''.join(f';{key}-{c}:{v}' for c,v in zip('rgba', values))
    css = DECL.sub(declaration, css)
    css = MIX.sub(lambda match:'rgba('+','.join(mixed(match))+')', css)
    if 'color-mix(' in css:
        raise ValueError('An unhandled color-mix expression requires an Android fallback')
    return css.replace('dvh','vh').replace('svh','vh')
