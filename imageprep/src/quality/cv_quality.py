import cv2
import os
import tqdm
import typing as tp

import cv2.typing

BRISQUE_MODEL_PATH = 'models/quality/brisque_model_live.yml'
BRISQUE_RANGE_PATH = 'models/quality/brisque_range_live.yml'
SHARPNESS_THRESHOLD = 80.
BRIGHTNESS_THRESHOLD = 200.
DARKNESS_THRESHOLD = 20.
BRISQUE_THRESHOLD = 30.


class CVQuality:
    def __init__(self):
        self.brisque = cv2.quality.QualityBRISQUE()

    def calculate_sharpness(self, gray: cv2.typing.MatLike) -> float:
        # Compute the Laplacian of the image
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        # Compute the variance of the Laplacian
        variance = laplacian.var()
        return variance

    def calculate_brightness(self, gray: cv2.typing.MatLike) -> float:
        # Compute the average brightness
        mean_brightness = gray.mean()
        return mean_brightness

    def calculate_brisque(self, image: cv2.typing.MatLike) -> float:
        scores = self.brisque.compute(
            image,
            model_file_path=BRISQUE_MODEL_PATH,
            range_file_path=BRISQUE_RANGE_PATH
        )
        return scores[0]

    def calculate_quality(self, img_path: str) -> tp.Tuple[float, float, float, bool]:
        try:
            img = cv2.imread(img_path)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            sharpness = self.calculate_sharpness(gray)
            brightness = self.calculate_brightness(gray)
            brisque = self.calculate_brisque(img)
        except Exception as e:
            raise type(e)(f"{str(e)} (file: {img_path})") from e
        sharpness_condition = sharpness >= SHARPNESS_THRESHOLD
        bright_condition = brightness < BRIGHTNESS_THRESHOLD
        dark_condition = brightness > DARKNESS_THRESHOLD
        brisque_condition = brisque < BRISQUE_THRESHOLD
        quality = all([
            sharpness_condition,
            bright_condition,
            dark_condition,
            brisque_condition
        ])
        return sharpness, brightness, brisque, quality



if __name__ == '__main__':
    import requests
    # jpeg_compressed_image
    jpeg_compressed_image = requests.get('https://www.unite.ai/wp-content/uploads/2021/09/jpeg-attrition.jpg')
    local_dir = 'data/test/quality'
    os.makedirs(local_dir, exist_ok=True)
    jpeg_compressed_path = os.path.join(local_dir, 'jpeg_compressed_image.jpg')
    with open(jpeg_compressed_path, 'wb') as f:
        f.write(jpeg_compressed_image.content)
    good_png_image = requests.get('https://onlinepngtools.com/images/examples-onlinepngtools/pendant-lamp-over-river.png')
    good_png_path = os.path.join(local_dir, 'good_png_image.png')
    with open(good_png_path, 'wb') as f:
        f.write(good_png_image.content)
    cvq = CVQuality()
    for img_path in [jpeg_compressed_path, good_png_path]:
        sharpness, brightness, brisque, quality = cvq.calculate_quality(img_path)
        print(os.path.basename(img_path))
        print(f'sharpness: {round(sharpness, 2)}')
        print(f'brightness: {round(brightness, 2)}')
        print(f'brisque: {round(brisque, 2)}')
        print(f'quality: {quality}')
        print()
