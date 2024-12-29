import os
import requests
import logging
from urllib.parse import urlparse
from dotenv import load_dotenv
import base64
from io import BytesIO

load_dotenv()
logger = logging.getLogger(__name__)

IMGUR_CLIENT_ID = os.getenv('IMGUR_CLIENT_ID')
IMGUR_CLIENT_SECRET = os.getenv('IMGUR_CLIENT_SECRET')

def download_image(url):
    """Télécharge l'image depuis l'URL"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
            'Accept-Language': 'fr,fr-FR;q=0.9,en;q=0.8',
            'Referer': 'https://www.jeuxvideo.com/'
        }
        
        logger.info(f"Downloading image with headers from: {url}")
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.content
    except Exception as e:
        logger.error(f"Erreur lors du téléchargement de l'image: {str(e)}")
        return None

def upload_to_imgur(image_url):
    """Upload an image to Imgur and return the new URL"""
    try:
        client_id = os.getenv('IMGUR_CLIENT_ID')
        if not client_id:
            logger.error("IMGUR_CLIENT_ID not found in environment variables")
            return None

        # Get the image first
        img_response = requests.get(image_url)
        if img_response.status_code != 200:
            logger.error(f"Failed to fetch image from {image_url}")
            return None

        # Upload to Imgur
        headers = {'Authorization': f'Client-ID {client_id}'}
        files = {'image': img_response.content}
        response = requests.post('https://api.imgur.com/3/image', headers=headers, files=files)

        if response.status_code == 200:
            imgur_url = response.json()['data']['link']
            logger.info(f"Successfully uploaded to Imgur: {imgur_url}")
            return imgur_url
        else:
            logger.error(f"Imgur upload failed: {response.text}")
            return None

    except Exception as e:
        logger.error(f"Error uploading to Imgur: {str(e)}")
        return None

def process_image_url(image_url, source_name):
    """Process image URL based on source"""
    if not image_url:
        return None
        
    # Special handling for JVC images
    if source_name == "JVC":
        logger.info(f"Processing JVC image: {image_url}")
        imgur_url = upload_to_imgur(image_url)
        if imgur_url:
            return imgur_url
            
    return image_url
