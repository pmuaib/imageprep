import argparse
import os
import re
import random
from concurrent.futures import ThreadPoolExecutor
import time
import requests
from selenium.webdriver.common.by import By
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# example run:
# python imageprep/src/collection/lpsg.py --thread_url https://www.lpsg.com/threads/drazenpn.5832241/ --output_dir data/test --order_by_reaction_score
# should download 9 images

# set with your own email and password
EMAIL = ''
PASSWORD = ''

ORDER_BY_REACTION_SCORE = 'order=th_mrp_reaction_score'


class LPSG:
    def __init__(
        self,
        thread_url: str,
        top_dir: str,
        order_by_reaction_score: bool = False,
        max_pages: int = 1000,
    ):
        if thread_url[-1] != '/':
            thread_url += '/'
        self.thread_url = thread_url
        self.gal_name = thread_url.split('/')[-2]
        self.top_dir = top_dir
        self.gal_dir = os.path.join(self.top_dir, self.gal_name)
        self.imgs_dir = os.path.join(self.gal_dir, 'imgs')
        os.makedirs(self.imgs_dir, exist_ok=True)
        self.driver = None
        self.order_by_reaction_score = order_by_reaction_score
        self.max_pages = max_pages

    def run(self):
        self.open_selenium()
        self.login()
        self.thread_loop()
        self.cleanup()

    def open_selenium(self):
        chrome_options = Options()
        chrome_options.add_argument('--incognito')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--no-sandbox')
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        # maximize window
        self.driver.maximize_window()

    def login(self):
        self.driver.get('https://www.lpsg.com/login')
        time.sleep(2)
        self.check_cloudflare()
        input_email = self.driver.find_element(By.NAME, 'login')
        email = EMAIL
        for char in email:
            input_email.send_keys(char)
            time.sleep(random.randint(1, 3) / 10.)
        input_password = self.driver.find_element(By.NAME, 'password')
        pw = PASSWORD
        for char in pw:
            input_password.send_keys(char)
            time.sleep(random.randint(1, 3) / 10.)
        buttons = self.driver.find_elements(By.TAG_NAME, 'button')
        for button in buttons:
            if button.get_attribute('class') == 'button--primary button button--icon button--icon--login rippleButton':
                button.click()
                break
        time.sleep(2)
        self.check_cloudflare()
        print('logged in')

    def get_attachments(self):
        unique_links = set(re.findall(r'https://www.lpsg.com/attachments/.*?(?=")', self.driver.page_source))
        return list(sorted(list(unique_links)))

    def get_pintwimg_imgs(self):
        # https://i.pinimg.com/
        unique_links = set(re.findall(r'https://i.pinimg.com/.*?(?=")', self.driver.page_source))
        # twimg
        unique_links.update(set(re.findall(r'https://pbs.twimg.com/.*?(?=")', self.driver.page_source)))
        # any link the ends in .jpg, .jpeg, .png
        unique_links.update(set(re.findall(r'https://.*?\.jpg.*?(?=")', self.driver.page_source)))
        unique_links.update(set(re.findall(r'https://.*?\.jpeg.*?(?=")', self.driver.page_source)))
        unique_links.update(set(re.findall(r'https://.*?\.png.*?(?=")', self.driver.page_source)))
        return list(sorted(list(unique_links)))

    def download_image_with_session(self, session: requests.Session, user_agent: str, img_url: str, save_path: str):
        # Create requests session with same cookies
        # Create requests session with same cookies
        try:
            if 'lpsg' in img_url:
                
                # Copy selenium headers
                headers = {
                    'User-Agent': user_agent
                }
                
                # Download image
                response = session.get(img_url, headers=headers, stream=True)
                if response.status_code == 200:
                    with open(save_path, 'wb') as f:
                        for chunk in response.iter_content(1024):
                            f.write(chunk)
            else:
                response = requests.get(img_url)
                with open(save_path, 'wb') as f:
                    f.write(response.content)
            
        except Exception as e:
            print(f'error in download_image_with_session: {img_url}', e)

    def get_lpsg_extension(self, img_url: str):
        return img_url.split('-')[-1].split('.')[0]

    def get_other_extension(self, img_url: str):
        if img_url.split('.')[-1] in ['jpg', 'jpeg', 'png', 'webp']:
            return img_url.split('.')[-1]
        elif '?format=jpg' in img_url:
            return 'jpg'
        elif '?format=jpeg' in img_url:
            return 'jpeg'
        elif '?format=png' in img_url:
            return 'png'
        elif '?format=webp' in img_url:
            return 'webp'
        elif 'jpg' in img_url:
            return 'jpg'
        elif 'jpeg' in img_url:
            return 'jpeg'
        elif 'png' in img_url:
            return 'png'
        elif 'webp' in img_url:
            return 'webp'
        else:
            return None

    def is_large_enough(self, path: str):
        from PIL import Image
        try:
            with Image.open(path) as img:
                return img.size[0]*img.size[1] > 1024*1024
        except Exception:
            return False

    def download_images(self, img_index: int):
        import uuid
        cookies = self.driver.get_cookies()
        session = requests.Session()
        for cookie in cookies:
            session.cookies.set(cookie['name'], cookie['value'])
        user_agent = self.driver.execute_script('return navigator.userAgent;')
        attachments = self.get_attachments()
        lpsg_exts = [self.get_lpsg_extension(attachment) for attachment in attachments]
        other_urls = self.get_pintwimg_imgs()
        other_exts = [self.get_other_extension(url) for url in other_urls]
        keep_other_urls = []
        keep_other_exts = []
        for url, ext in zip(other_urls, other_exts):
            if ext is not None:
                keep_other_urls.append(url)
                keep_other_exts.append(ext)
        urls = attachments + keep_other_urls
        exts = lpsg_exts + keep_other_exts
        save_paths = []
        for ext in exts:
            if ext in ['jpg', 'jpeg', 'png']:
                path = os.path.join(self.imgs_dir, f'{uuid.uuid4()}.{ext}')
                save_paths.append(path)
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(
                    self.download_image_with_session,
                    session,
                    user_agent,
                    url,
                    save_path
                ) for url, save_path in zip(urls, save_paths)
            ]
            for future in futures:
                future.result()
        to_keep = []
        for save_path in save_paths:
            if os.path.exists(save_path):
                if not self.is_large_enough(save_path):
                    os.remove(save_path)
                else:
                    to_keep.append(save_path)
        for save_path in to_keep:
            ext = save_path.split('.')[-1]
            os.rename(save_path, os.path.join(self.imgs_dir, f'{img_index}.{ext}'))
            img_index += 1
        return img_index

    def next_link_available(self, next_url: str):
        links = self.driver.find_elements(By.TAG_NAME, 'a')
        next_link_found = False
        for link in links:
            href = link.get_attribute('href')
            if href is not None:
                if next_url in href:
                    next_link_found = True
        return next_link_found

    def thread_loop(self):
        page = 1
        first_page = self.thread_url
        page_format = 'page-{page}'
        img_index = 0
        while True:
            if page == 1:
                page_url = first_page
            else:
                page_url = first_page + page_format.format(page=page)
            if self.order_by_reaction_score:
                page_url += f'?{ORDER_BY_REACTION_SCORE}'
            try:
                self.driver.get(page_url)
                time.sleep(random.randint(2, 4))
            except Exception as e:
                print(e)
                break
            img_index = self.download_images(img_index)
            next_url = first_page + page_format.format(page=page+1)
            if page >= self.max_pages or not self.next_link_available(next_url):
                break
            page += 1

    def check_cloudflare(self):
        moment_check = 'Just a moment...' in self.driver.page_source
        human_check = 'you are human' in self.driver.page_source
        if moment_check or human_check:
            self.cleanup()
            raise Exception('Cloudflare detected')

    def cleanup(self):
        if self.driver:
            self.driver.close()


if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument('--thread_url', type=str, required=True)
    args.add_argument('--output_dir', type=str, required=True)
    args.add_argument('--order_by_reaction_score', action='store_true', default=False)
    args.add_argument('--max_pages', type=int, required=False, default=1000)
    args = args.parse_args()
    thread_url = args.thread_url
    output_dir = args.output_dir
    order_by_reaction_score = args.order_by_reaction_score
    max_pages = args.max_pages
    lpsg = LPSG(
        thread_url=thread_url,
        top_dir=output_dir,
        order_by_reaction_score=order_by_reaction_score,
        max_pages=max_pages,
    )
    try:
        lpsg.run()
    except Exception as e:
        print(e)
        lpsg.cleanup()
