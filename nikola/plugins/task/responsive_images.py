"""Task plugin: create resized copies (photo-480w.jpg, ...) of images.

It follows the same pattern as scale_images.py: the class is both a Task and
an ImageProcessor, and the real resizing is done by resize_image().
It only runs when RESPONSIVE_IMAGES = True in conf.py.
"""

import os

from nikola import responsive, utils
from nikola.image_processing import ImageProcessor
from nikola.plugin_categories import Task


class ResponsiveImages(Task, ImageProcessor):
    """Create several widths of every image, for use in srcset."""

    name = "responsive_images"

    def make_variants(self, src, targets, bounds):
        """Write all resized copies of one image (the image is opened only once)."""
        self.resize_image(
            src,
            dst_paths=targets,
            max_sizes=bounds,
            bigger_panoramas=False,  # panoramas must not get the 4x limit here
            preserve_exif_data=self.kw['preserve_exif_data'],
            exif_whitelist=self.kw['exif_whitelist'],
            preserve_icc_profiles=self.kw['preserve_icc_profiles'],
        )

    def process_tree(self, src_folder, dst_folder):
        """Yield one task for each image in a source folder (and its sub folders)."""
        for root, _dirs, files in os.walk(src_folder, followlinks=True):
            relative = os.path.relpath(root, src_folder)
            dst_dir = os.path.normpath(os.path.join(dst_folder, relative))

            for filename in sorted(files):
                # Skip SVG/GIF/etc. and files that are already resized copies.
                if not responsive.is_supported(filename):
                    continue
                if responsive.is_variant(filename):
                    continue

                src_file = os.path.join(root, filename)

                try:
                    if responsive.is_animated(src_file):
                        continue  # Nikola copies these unchanged
                    src_w, src_h = responsive.source_size(src_file)
                except Exception as error:  # unreadable or damaged image
                    self.logger.warning(
                        'responsive_images: skipping {}: {}'.format(src_file, error))
                    continue

                # Width of the image as Nikola publishes it, then the widths
                # smaller than that (so nothing is ever enlarged).
                published = responsive.effective_width(src_w, src_h, self.kw['max_image_size'])
                wanted = responsive.widths_for(published, self.kw['widths'])
                if not wanted:
                    continue

                targets = []
                bounds = []
                for width in wanted:
                    name = responsive.variant_name(filename, width)
                    targets.append(os.path.join(dst_dir, name))
                    bounds.append(responsive.bound_for_width(width, src_w, src_h))

                yield {
                    'name': os.path.join(dst_dir, filename),
                    'file_dep': [src_file],
                    'targets': targets,
                    'actions': [(self.make_variants, (src_file, targets, bounds))],
                    'clean': True,
                }

    def gen_tasks(self):
        """Create the tasks (nothing happens unless RESPONSIVE_IMAGES is True)."""
        yield self.group_task()

        config = self.site.config
        if not config.get('RESPONSIVE_IMAGES', False):
            return

        # Same style as scale_images.py: settings in one dict. When any of them
        # changes in conf.py, config_changed makes the images be redone.
        self.kw = {
            'widths': list(config.get('RESPONSIVE_IMAGE_WIDTHS', responsive.DEFAULT_WIDTHS)),
            'max_image_size': config['MAX_IMAGE_SIZE'],
            'output_folder': config['OUTPUT_FOLDER'],
            'preserve_exif_data': config['PRESERVE_EXIF_DATA'],
            'exif_whitelist': config['EXIF_WHITELIST'],
            'preserve_icc_profiles': config['PRESERVE_ICC_PROFILES'],
        }
        filters = config['FILTERS']

        # {source folder: folder inside output}, for post images and galleries.
        folders = {}
        folders.update(config['IMAGE_FOLDERS'])
        folders.update(config.get('GALLERY_FOLDERS', {}))

        for src_folder, output_name in folders.items():
            if not os.path.isdir(src_folder):
                continue
            dst_folder = os.path.join(self.kw['output_folder'], output_name)
            for task in self.process_tree(src_folder, dst_folder):
                task['basename'] = self.name
                task['uptodate'] = [utils.config_changed(self.kw)]
                yield utils.apply_filters(task, filters)
