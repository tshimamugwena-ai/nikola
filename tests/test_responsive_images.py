"""Tests for Partner A's code: the shared helpers and the width calculations."""

import logging
import os

import pytest
from PIL import Image

from nikola import responsive

WIDTHS = [480, 800, 1200]


def make_image(path, size):
    """Helper: save a plain red image of the given size."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    Image.new('RGB', size, (200, 30, 30)).save(path)


def thumbnail_width(size, bound):
    """Helper: width Pillow gives when fitting an image into a bound x bound square.

    This is what Nikola's resize_image() does internally.
    """
    image = Image.new('RGB', size)
    image.thumbnail((bound, bound), Image.Resampling.LANCZOS)
    return image.width


# ---------- naming ----------

def test_variant_name():
    assert responsive.variant_name('photo.jpg', 800) == 'photo-800w.jpg'


def test_variant_name_with_folder_and_dots():
    assert responsive.variant_name('/images/a.b.png', 480) == '/images/a.b-480w.png'


def test_is_variant():
    assert responsive.is_variant('photo-800w.jpg') is True
    assert responsive.is_variant('photo.jpg') is False
    assert responsive.is_variant('photo-800.jpg') is False


def test_is_supported():
    assert responsive.is_supported('a.jpg') is True
    assert responsive.is_supported('a.JPG') is True
    assert responsive.is_supported('a.webp') is True
    assert responsive.is_supported('logo.svg') is False
    assert responsive.is_supported('animation.gif') is False


# ---------- choosing widths ----------

def test_widths_for_large_image():
    assert responsive.widths_for(1000, WIDTHS) == [480, 800]


def test_widths_for_never_upscales():
    assert responsive.widths_for(300, WIDTHS) == []


def test_widths_for_equal_width_is_skipped():
    assert responsive.widths_for(800, WIDTHS) == [480]


def test_widths_for_removes_duplicates_and_sorts():
    assert responsive.widths_for(2000, [800, 480, 800]) == [480, 800]


def test_build_srcset():
    result = responsive.build_srcset('/images/p.jpg', 1000, WIDTHS)
    expected = '/images/p-480w.jpg 480w, /images/p-800w.jpg 800w, /images/p.jpg 1000w'
    assert result == expected


# ---------- published width (copies Nikola's resize rules) ----------

def test_effective_width_landscape_is_limited():
    assert responsive.effective_width(4000, 3000, 1280) == 1280


def test_effective_width_portrait_is_limited_by_height():
    assert responsive.effective_width(3000, 4000, 1280) == 960


def test_effective_width_small_image_unchanged():
    assert responsive.effective_width(800, 600, 1280) == 800


def test_effective_width_without_limit():
    assert responsive.effective_width(4000, 3000, 0) == 4000


def test_effective_width_panorama_gets_bigger_limit():
    # width is more than 3 times the height, so the limit is 4 * 1280 = 5120
    assert responsive.effective_width(6000, 1000, 1280) == 5120


def test_effective_width_small_panorama_unchanged():
    assert responsive.effective_width(4000, 1000, 1280) == 4000


# ---------- converting a width into resize_image's square size ----------

def test_bound_for_landscape_is_the_width():
    assert responsive.bound_for_width(480, 1000, 500) == 480


def test_bound_for_portrait_is_larger_than_the_width():
    assert responsive.bound_for_width(240, 500, 1000) == 480


def test_bound_gives_the_requested_width_for_landscape():
    for size in [(1000, 500), (4000, 3000), (2000, 2000)]:
        bound = responsive.bound_for_width(480, *size)
        assert thumbnail_width(size, bound) == 480


def test_bound_gives_the_requested_width_for_portrait_within_one_pixel():
    for size in [(500, 1000), (3000, 4000), (1500, 2000)]:
        bound = responsive.bound_for_width(400, *size)
        assert abs(thumbnail_width(size, bound) - 400) <= 1


# ---------- reading image files ----------

def test_source_size_applies_exif_rotation(tmp_path):
    # A 1000x500 photo with the EXIF tag "rotate 90 degrees" is really portrait.
    path = str(tmp_path / 'rotated.jpg')
    exif = Image.Exif()
    exif[0x0112] = 6
    Image.new('RGB', (1000, 500)).save(path, exif=exif)

    assert responsive.source_size(path) == (500, 1000)


def test_published_width(tmp_path):
    path = str(tmp_path / 'big.jpg')
    make_image(path, (4000, 3000))
    assert responsive.published_width(path, 1280) == 1280


def test_is_animated(tmp_path):
    still = str(tmp_path / 'still.png')
    make_image(still, (50, 50))
    assert responsive.is_animated(still) is False

    moving = str(tmp_path / 'moving.png')
    frames = [Image.new('RGB', (50, 50), (i * 40, 0, 0)) for i in range(3)]
    frames[0].save(moving, save_all=True, append_images=frames[1:], duration=100)
    assert responsive.is_animated(moving) is True


# ---------- integration with Nikola's own ImageProcessor ----------

def test_resize_image_produces_the_variants(tmp_path):
    """Nikola's resize_image() with our bounds gives files of the wanted widths."""
    pytest.importorskip('piexif')  # needed by nikola.image_processing
    from nikola.image_processing import ImageProcessor

    class Processor(ImageProcessor):
        logger = logging.getLogger('test_responsive_images')

    source = str(tmp_path / 'photo.jpg')
    make_image(source, (1000, 500))
    wanted = [480, 800]
    targets = [str(tmp_path / 'out' / responsive.variant_name('photo.jpg', w))
               for w in wanted]
    os.makedirs(str(tmp_path / 'out'))
    bounds = [responsive.bound_for_width(w, 1000, 500) for w in wanted]

    Processor().resize_image(source, dst_paths=targets, max_sizes=bounds,
                             bigger_panoramas=False)

    for target, width in zip(targets, wanted):
        with Image.open(target) as image:
            assert image.size == (width, width // 2)
