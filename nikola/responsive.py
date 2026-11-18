"""Helpers shared by the image task (Partner A) and the HTML filter (Partner B).

Naming rule we agreed on:  photo.jpg  ->  photo-800w.jpg
(<basename>-<width>w.<ext>)

The actual resizing is NOT done here. The task plugin reuses Nikola's own
ImageProcessor.resize_image(). This module only decides names and widths.
"""

import os
import re

from PIL import Image

# Only these formats get variants. SVG is vector, GIF can be animated.
SUPPORTED_EXTS = ('.jpg', '.jpeg', '.png', '.webp')

# Default settings (can be changed in conf.py)
DEFAULT_WIDTHS = [480, 800, 1200, 1600]
DEFAULT_SIZES = '100vw'

# Matches names that end in "-<number>w", e.g. "photo-800w"
VARIANT_PATTERN = re.compile(r'-\d+w$')


def is_supported(path):
    """Return True if the file is a format we make variants of."""
    extension = os.path.splitext(path)[1].lower()
    return extension in SUPPORTED_EXTS


def is_variant(path):
    """Return True if the file is already a resized copy (like photo-800w.jpg).

    We use this so we never resize our own output.
    """
    name_without_ext = os.path.splitext(path)[0]
    return VARIANT_PATTERN.search(name_without_ext) is not None


def variant_name(path, width):
    """Build the name of a resized copy: photo.jpg and 800 -> photo-800w.jpg."""
    name, extension = os.path.splitext(path)
    return name + '-' + str(width) + 'w' + extension


def effective_width(width, height, max_size=0):
    """Width of the image after Nikola's scale_images task has processed it.

    This copies the rules of ImageProcessor.resize_image():
    * images are shrunk to fit inside a max_size x max_size square
      (max_size 0 means no limit), and never enlarged;
    * panoramas (width more than 3 times the height) get a bigger limit:
      up to 4 times max_size.
    """
    if max_size <= 0:
        return width
    if width <= max_size and height <= max_size:
        return width

    limit = max_size
    if width > 3 * height:  # panorama
        limit = min(width, max_size * 4)

    longest_side = max(width, height)
    if longest_side <= limit:
        return width
    return max(1, round(width * limit / longest_side))


def widths_for(original_width, widths):
    """Pick which widths to generate.

    Only widths smaller than the original are used, so we never upscale.
    """
    result = []
    for w in widths:
        w = int(w)
        if 0 < w < original_width and w not in result:
            result.append(w)
    result.sort()
    return result


def bound_for_width(width, source_width, source_height):
    """Turn a wanted width into the 'square size' that resize_image() expects.

    resize_image() fits the image inside a square, so it limits the LONGEST
    side. For landscape or square images that is the width, so the numbers are
    the same. For portrait images the square size must be larger than the
    width. Portrait results can be off by 1 pixel because of rounding.
    """
    if source_width >= source_height:
        return width
    return max(1, round(width * source_height / source_width))


def oriented_size(image):
    """Return (width, height) of a Pillow image, taking EXIF rotation into account."""
    width, height = image.size
    try:
        orientation = image.getexif().get(0x0112)  # 0x0112 is the EXIF orientation tag
    except Exception:
        orientation = None  # broken EXIF data should not stop the build
    # Values 5-8 mean the photo is turned on its side, so width and height swap.
    if orientation in (5, 6, 7, 8):
        width, height = height, width
    return width, height


def source_size(path):
    """Return (width, height) of an image file, upright."""
    with Image.open(path) as image:
        return oriented_size(image)


def is_animated(path):
    """Return True for animated images (animated WebP/PNG).

    Nikola copies these unchanged, so we must not make variants of them.
    (JPEGs are never treated as animated, same as in Nikola, issue #3332.)
    """
    if os.path.splitext(path)[1].lower() in ('.jpg', '.jpeg'):
        return False
    with Image.open(path) as image:
        return getattr(image, 'n_frames', 1) > 1


def published_width(path, max_size=0):
    """Width the image will have in the output folder."""
    width, height = source_size(path)
    return effective_width(width, height, max_size)


def build_srcset(url, original_width, widths):
    """Build the text for an HTML srcset attribute.

    Example: "/a-480w.jpg 480w, /a-800w.jpg 800w, /a.jpg 1000w"
    """
    parts = []
    for w in widths_for(original_width, widths):
        parts.append(variant_name(url, w) + ' ' + str(w) + 'w')
    parts.append(url + ' ' + str(original_width) + 'w')  # the original goes last
    return ', '.join(parts)
