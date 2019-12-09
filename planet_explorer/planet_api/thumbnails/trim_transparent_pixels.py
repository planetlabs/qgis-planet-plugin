import os
import logging

# noinspection PyPackageRequirements
from PIL import Image

LOG_LEVEL = os.environ.get('PYTHON_LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)


def trim_transparent_pixels(orig_path, trimmed_path):

    image: Image = Image.open(orig_path)
    image.load()
    image_size = image.size
    image_box = image.getbbox()
    image_bands = image.getbands()

    if len(image_bands) == 1:
        image = image.convert("RGBA")
    image_bands = image.getbands()

    if len(image_bands) < 4:
        # Skip images with no alpha band
        log.debug('Image has less than 4 bands')
        return

    # rgb_image = Image.new("RGB", image_size, (0, 0, 0))
    # rgb_image.paste(image, mask=image_bands[3])
    # Convert all rgba(n, n, n, 0) to rgba(0, 0, 0, 0) so getbbox() works
    # black = Image.new("RGBA", image_size)
    # rgb_image = Image.composite(image, black, image)
    rgb_image: Image = Image.new("RGBA", image_size, (0, 0, 0, 0))
    alpha_channel = image.getchannel('A')
    rgb_image.paste(image, mask=alpha_channel)
    cropped_box = rgb_image.getbbox()

    # if image_box != cropped_box:
    cropped = image.crop(cropped_box)
    print(orig_path, "Size:", image_size, "New Size:", cropped_box)
    cropped.save(trimmed_path)
    # else:
    #     log.debug('Image bbox and cropped bbox are the same')


if __name__ == "__main__":
    size = '512'
    orig_file = f'thumb_{size}_orig.png'
    trimmed_file = f'thumb_{size}.png'
    trim_transparent_pixels(orig_file, trimmed_file)
