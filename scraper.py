from bs4 import BeautifulSoup
import requests
import time
import logging
from article_tracker import clean_article_content

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_main_image(url, soup=None):
    """Extrait l'URL de l'image principale d'un article"""
    try:
        logger.info(f"Extracting main image from URL: {url}")
        if not soup:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')

        # Special handling for developpez.com
        if 'developpez.com' in url:
            # Look for images in article content first
            content_images = soup.select('div[style*="text-align: center"] img[src*="/public/images/"]')
            if content_images:
                image_url = content_images[0].get('src')
                if image_url and is_valid_image_url(image_url):
                    logger.info(f"Found developpez.com content image: {image_url}")
                    return image_url

        # Rechercher l'image principale avec différents sélecteurs courants
        possible_selectors = [
            'meta[property="og:image"]',
            'meta[name="twitter:image"]',
            '.article-featured-image img',
            '.post-thumbnail img',
            'article img',
            '.entry-content img',
            'img.wp-post-image',
            'figure img',
            '.main-image img',
            '.featured-image img'
        ]

        for selector in possible_selectors:
            if selector.startswith('meta'):
                element = soup.select_one(selector)
                if element and element.get('content'):
                    logger.info(f"Found image using selector {selector}: {element['content']}")
                    return element['content']
            else:
                element = soup.select_one(selector)
                if element and element.get('src'):
                    logger.info(f"Found image using selector {selector}: {element['src']}")
                    return element['src']
        
        # If no image found, try to find the first valid image in the article body
        for img in soup.find_all('img'):
            if img.get('src') and is_valid_image_url(img.get('src')):
                logger.info(f"Found image in article body: {img['src']}")
                return img['src']
        
        logger.warning(f"No main image found for URL: {url}")
        return None

    except Exception as e:
        logger.error(f"Erreur lors de l'extraction de l'image: {str(e)}")
        return None

def is_valid_image_url(url):
    """Vérifie si l'URL de l'image est valide et n'est pas un logo"""
    if not url:
        return False
        
    # Special case for developpez.com
    if 'developpez.com' in url:
        if '/public/images/' in url:
            return True
        if '/images/logos/' in url:
            return False
            
    # Liste des motifs à exclure
    excluded_patterns = [
        'logo', 
        'logos',
        'favicon',
        'fzn',
        'header',
        'footer',
        'icon',
        'banner',
        '-min.png',
        'site-icon',
        'site-logo',
        'brand'
    ]
    
    for pattern in excluded_patterns:
        if pattern in url:
            return False
            
    return True

def get_full_article(url):
    """Récupère le contenu complet d'un article et son image"""
    try:
        logger.info(f"Fetching full article from URL: {url}")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Trouver l'image principale
        image_url = extract_main_image(url, soup)
        
        # Trouver le contenu principal
        content = None
        for selector in [
            'article', '.article-content', '.post-content', 
            '[itemprop="articleBody"]', '.entry-content'
        ]:
            main_content = soup.select_one(selector)
            if main_content:
                content = clean_article_content(main_content)
                break
        
        if not content:
            content = clean_article_content(soup.get_text())
            
        logger.info(f"Successfully fetched article content from URL: {url}")
        return content, image_url
        
    except Exception as e:
        logger.error(f"Erreur lors du scraping de {url}: {e}")
        return None, None

# Exemple d'utilisation
if __name__ == "__main__":
    test_url = "https://example.com/article"
    content, image = get_full_article(test_url)
    if content:
        print("Contenu trouvé:", content[:500], "...")
        if image:
            print("Image trouvée:", image)
    else:
        print("Impossible de récupérer le contenu")
