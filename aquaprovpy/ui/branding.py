"""Shared interface colors drawn from the supplied AquaProv logo."""
from pathlib import Path
import re


LOGO_PATH = Path(__file__).resolve().parents[1] / 'assets' / 'icons' / 'Logo.png'
ICON_PATH = LOGO_PATH.with_name('icon.png')
COLORS = {
    'background': '#f0f7fa',
    'surface': '#ffffff',
    'soft': '#f7fbfc',
    'wash': '#e7f4f7',
    'navigation': '#e2f0f5',
    'hover': '#d8edf2',
    'selected': '#cce9ef',
    'border': '#cfdee5',
    'ink': '#07385b',
    'muted': '#526f80',
    'disabled': '#829aa8',
    'navy': '#00365d',
    'teal': '#006d75',
    'teal_hover': '#005962',
    'cyan': '#0095bf',
    'banner_end': '#def1f5',
}


def brand_stylesheet(source):
    """Resolve named colors without treating QSS braces as formatting syntax."""
    return re.sub(r'@([a-z_]+)@', lambda match: COLORS[match[1]], source)
