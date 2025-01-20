import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from PIL import Image, UnidentifiedImageError
import requests
import re
import random
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
import time
from selenium.common.exceptions import ElementNotInteractableException
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import subprocess

# example run:
# python imageprep/src/collection/adonismale.py --gallery_url 'https://www.adonismale.com/gallery/album/69775-%F0%9F%96%8C-with-the-pencil-erect/' --output_dir data/test/
# should download 64 images


# this should work on Mac, but replace with your own path
CHROME_PATH = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
# this will save a new Profile in the data directory
CHROME_USER_DATA_DIR = 'data/Library/Application Support/Google/Chrome/Profile 1'
# set these to your own user email and password
ADONISMALE_EMAIL = ''
ADONISMALE_PASSWORD = ''
MIN_IMG_SIZE = 1024*1024


def download_and_save(j: int, url: str, img_dir: str, max_i: int):
    if '.gif' not in url:
        try:
            img = Image.open(requests.get('https://' + url, stream=True).raw)
            # save with the same file extension as the original
            img.save(os.path.join(img_dir, f"{max_i + j + 1}.{url.split('.')[-1]}"))
        except UnidentifiedImageError:
            print(f"{j}: UnidentifiedImageError")
        except OSError:
            print(f"{j}: OSError")


def download_images(urls: list[str], gal_dir: str):
    img_dir = os.path.join(gal_dir, 'imgs')
    os.makedirs(img_dir, exist_ok=True)
    current_files = list(os.listdir(img_dir))
    if len(current_files) > 0:
        max_i = max([int(f.split('.')[0]) for f in current_files])
    else:
        max_i = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        for i in range(0, len(urls), 128):
            batch_urls = urls[i:i+128]
            list(executor.map(lambda j, url: download_and_save(j+i, url, img_dir, max_i), 
                            range(len(batch_urls)), batch_urls))
            if i + 128 < len(urls):  # Don't sleep after the last batch
                time.sleep(5)


class Adonis:
    def __init__(
        self,
        gallery_url: str,
        top_dir: str,
        subdir: str = None,
    ):
        gal_name = gallery_url.split('album/')[1].replace('/', '')
        if subdir:
            top_dir = os.path.join(top_dir, subdir)
        self.gal_dir = os.path.join(top_dir, gal_name)
        self.webpages_dir = os.path.join(self.gal_dir, 'webpages')
        os.makedirs(self.webpages_dir, exist_ok=True)
        self.url_txt = os.path.join(self.gal_dir, 'urls.txt')
        self.gallery_url = gallery_url
        self.subdir = subdir
        self.driver = None

    def run(self):
        if os.path.exists(self.url_txt):
            return
        self.setup()
        self.navigate_to_gallery()
        self.loop_through_pages()
        self.onefile()
        self.cleanup()

    def setup(self):
        self.open_chrome()
        self.attach_selenium()
        self.login()

    def open_chrome(self):
        subprocess.Popen(
            [
                CHROME_PATH,
                '-remote-debugging-port=9222',
                '--incognito',
                f"--user-data-dir={CHROME_USER_DATA_DIR}",
                'https://adonismale.com/login/'
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(3)
        print('opened chrome')

    def attach_selenium(self):
        print('attaching selenium')
        # incognito
        chrome_options = Options()
        chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--no-sandbox')
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        # maximize window
        self.driver.maximize_window()
        self.check_cloudflare()

    def login(self):
        print('logging in')
        input_email = self.driver.find_element(By.NAME, 'auth')
        email = ADONISMALE_EMAIL
        for char in email:
            input_email.send_keys(char)
            time.sleep(random.randint(1, 3) / 10.)
        input_password = self.driver.find_element(By.NAME, 'password')
        pw = ADONISMALE_PASSWORD
        for char in pw:
            input_password.send_keys(char)
            time.sleep(random.randint(1, 3) / 10.)
        signin_button = self.driver.find_element(By.NAME, '_processLogin')
        self.driver.execute_script("arguments[0].click();", signin_button)
        time.sleep(random.randint(1, 3))
        self.check_cloudflare()

    def navigate_to_gallery(self):
        self.driver.get(self.gallery_url)
        time.sleep(random.randint(1, 3))
        self.check_cloudflare()
        thumbnail_size_buttons = self.driver.find_elements(By.CLASS_NAME, 'ipsCursor_pointer')
        big_button = None
        for button in thumbnail_size_buttons:
            if button.get_attribute('value') == 'large':
                big_button = button
                break
        big_button.click()
        self.check_cloudflare()

    def get_next_button(self):
        try:
            element = WebDriverWait(self.driver, timeout=20).until(
                EC.presence_of_element_located((By.CLASS_NAME, "ipsPagination_next"))
            )
            return element
        except Exception:
            return None

    def loop_through_pages(self):
        timeout = 10*60
        start_time = time.time()
        i = 0
        while time.time() - start_time < timeout:
            source_ = self.driver.page_source
            self.parse_page(source_, i)
            next_button = self.get_next_button()
            if next_button:
                try:
                    next_button.click()
                    time.sleep(random.randint(1, 2))
                except ElementNotInteractableException:
                    break
            else:
                break
            i += 1

    def parse_tags(self, img_tag):
        width_search = re.search(r'width="([^"]+)"', img_tag)
        height_search = re.search(r'height="([^"]+)"', img_tag)
        src_search = re.search(r'src="([^"]+)"', img_tag)
        if width_search and height_search and src_search:
            src = src_search.group(1)
            width = width_search.group(1)
            height = height_search.group(1) 
            return src[2:], int(width), int(height)
        else:
            return None

    def parse_page(self, html_text: str, i: int):
        imgs = []
        tags = re.findall(r'<img[^>]*src="//cdngallery\.adonismale\.com[^>]*>', html_text)
        for tag in tags:
            img = self.parse_tags(tag)
            if img:
                imgs.append(img)
        large_imgs = [img for img in imgs if img[1]*img[2] >= MIN_IMG_SIZE]
        # write all urls to {gal_dir}/urls.txt
        with open(os.path.join(self.webpages_dir, f'{i}.txt'), 'w') as f:
            for img in large_imgs:
                f.write(f"{img[0]}\n")

    def onefile(self):
        imgs = []
        img_txts = list(sorted(os.listdir(self.webpages_dir)))
        for img_txt in img_txts:
            with open(os.path.join(self.webpages_dir, img_txt), 'r') as f:
                img_txt_text = f.read()
            imgsi = img_txt_text.strip().split('\n')
            imgs.extend(imgsi)
        with open(self.url_txt, 'w') as f:
            for img in imgs:
                f.write(f"{img}\n")

    def check_cloudflare(self):
        moment_check = 'Just a moment...' in self.driver.page_source
        human_check = 'you are human' in self.driver.page_source
        if moment_check or human_check:
            self.cleanup()
            raise Exception('Cloudflare detected')

    def cleanup(self):
        if self.driver:
            self.driver.close()


def process_gallery_url(gallery_url: str, output_dir: str, n_tries: int = 3):
    success = False
    for i in range(n_tries):
        if success:
            continue
        adonis = Adonis(
            gallery_url=gallery_url,
            top_dir=output_dir,
        )
        try:
            adonis.run()
            success = True
            with open(adonis.url_txt, 'r') as f:
                urls = [url for url in f.read().strip().split('\n') if url]
            download_images(urls=urls, gal_dir=adonis.gal_dir)
        except Exception as e:
            print(e)
            adonis.cleanup()
            print(f'failed to process gallery {gallery_url} ({i+1}/{n_tries})')
            print(f'sleeping for {i*30} seconds')
            time.sleep(i*30)


def process_gallery_json(gallery_json_path: str, output_dir: str, n_tries: int = 3):
    with open(gallery_json_path, 'r') as f:
        gallery_json = json.load(f)
    for subdir in gallery_json.keys():
        for gallery_url in gallery_json[subdir]:
            success = False
            for i in range(n_tries):
                if success:
                    continue
                adonis = Adonis(
                    gallery_url=gallery_url,
                    subdir=subdir,
                    top_dir=output_dir,
                )
                try:
                    adonis.run()
                    success = True
                    break
                except Exception as e:
                    print(e)
                    adonis.cleanup()
                    print(f'failed to process gallery {gallery_url} ({i+1}/{n_tries})')
                    print(f'sleeping for {i*30} seconds')
                    time.sleep(i*30)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--gallery_url', type=str)
    parser.add_argument('--output_dir', type=str)
    args = parser.parse_args()
    process_gallery_url(args.gallery_url, args.output_dir)
