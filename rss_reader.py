import feedparser
from datetime import datetime
import time
import re
import json
import os
import logging
from scraper import extract_main_image, get_full_article  # Ajout de l'import
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROBLEMATIC_DOMAINS = [
    'fredzone.org',
    'clubic.com',
    '*.developpez.com',
    # Ajouter d'autres domaines qui nécessitent le scraping
]

def is_problematic_domain(domain):
    """Check if the domain matches any problematic domain pattern."""
    for prob_domain in PROBLEMATIC_DOMAINS:
        if prob_domain.startswith('*.'):
            if domain.endswith(prob_domain[1:]):
                return True
        elif prob_domain == domain:
            return True
    return False

IMAGE_CACHE_FILE = 'image_cache.json'
RSS_CACHE_DURATION = 300  # 5 minutes en secondes

@lru_cache(maxsize=100)
def parse_feed_cached(url):
    """Cache les résultats du parsing RSS pour 5 minutes"""
    return feedparser.parse(url)

def load_image_cache():
    if os.path.exists(IMAGE_CACHE_FILE):
        try:
            with open(IMAGE_CACHE_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_image_cache(cache):
    with open(IMAGE_CACHE_FILE, 'w') as f:
        json.dump(cache, f)

def is_valid_image_url(url):
    """Vérifie si l'URL de l'image est valide et n'est pas un logo"""
    if not url:
        return False
        
    # Liste des motifs à exclure
    excluded_patterns = [
        'logo', 
        'logos',  # Exclude URLs containing "logos"
        'favicon',
        'fzn',
        'header',
        'footer',
        'icon',
        'banner',
        '-min.png',  # Format courant pour les logos minifiés
        'site-icon',
        'site-logo',
        'brand'
    ]
    
    # Vérifier si l'URL contient un des motifs exclus
    url_lower = url.lower()
    for pattern in excluded_patterns:
        if pattern in url_lower:
            return False
            
    # Vérifier la taille minimale (pour éviter les icônes)
    if 'icon' in url_lower or any(dim in url_lower for dim in ['16x16', '32x32', '64x64']):
        return False

    # Vérifier les extensions d'image typiques des logos
    if url_lower.endswith(('.ico', '.svg')):
        return False
        
    return True

def extract_image_from_html(html_content):
    """Extrait l'URL de la première image valide d'un contenu HTML"""
    if not html_content:
        return None
        
    # Recherche toutes les balises img avec src
    img_pattern = r'<img[^>]+src=[\'"](https?://[^\'"]+)[\'"]'
    matches = re.finditer(img_pattern, html_content)
    
    # Teste chaque image jusqu'à en trouver une valide
    for match in matches:
        image_url = match.group(1)
        if is_valid_image_url(image_url):
            return image_url
            
    return None

def parse_date(entry):
    """Extrait et formate la date de l'article en vérifiant plusieurs champs possibles"""
    date_fields = [
        'published_parsed',
        'updated_parsed',
        'created_parsed',
        'date_parsed'
    ]

    for field in date_fields:
        if hasattr(entry, field) and getattr(entry, field):
            try:
                return datetime(*getattr(entry, field)[:6]).isoformat()
            except Exception as e:
                logger.error(f"Erreur de parsing de la date ({field}): {str(e)}")
                continue

    # Vérification des champs de date non parsés
    raw_date_fields = [
        'published',
        'updated',
        'created',
        'date',
        'dc:date'
    ]

    for field in raw_date_fields:
        if hasattr(entry, field) and getattr(entry, field):
            try:
                raw_date = getattr(entry, field)
                parsed_date = feedparser._parse_date(raw_date)
                if parsed_date:
                    return datetime(*parsed_date[:6]).isoformat()
            except Exception as e:
                logger.error(f"Erreur de parsing de la date brute ({field}): {str(e)}")
                continue

    return None

def process_entry_image(entry, image_cache):
    """Traite l'extraction d'image pour une entrée"""
    if entry.link in image_cache:
        return image_cache[entry.link]
        
    domain = urlparse(entry.link).netloc
    if is_problematic_domain(domain):
        logger.info(f"Scraping image for problematic domain: {domain}")
        scraped_image = extract_main_image(entry.link)
        if scraped_image and is_valid_image_url(scraped_image):
            image_cache[entry.link] = scraped_image
            return scraped_image
    return None

load_dotenv()

def process_single_entry(entry, image_cache):
    """Traite un seul article et retourne l'entrée mise à jour"""
    logger.info(f"Processing entry: {entry.link}")
    # Nettoyage du titre
    if hasattr(entry, 'title'):
        entry.title = entry.title.replace("Actualité : ", "", 1)
    
    # Recherche d'image dans le flux RSS d'abord
    image_url = None
    potential_images = []
    
    # Collecter les images du flux RSS
    if hasattr(entry, 'description'):
        img = extract_image_from_html(entry.description)
        if img and is_valid_image_url(img):
            potential_images.append(img)
            
    if hasattr(entry, 'content') and entry.content:
        img = extract_image_from_html(entry.content[0].value)
        if img and is_valid_image_url(img):
            potential_images.append(img)
            
    if 'media_content' in entry and entry.media_content:
        img = entry.media_content[0]['url']
        if is_valid_image_url(img):
            potential_images.append(img)
            
    if 'media_thumbnail' in entry and entry.media_thumbnail:
        img = entry.media_thumbnail[0]['url']
        if is_valid_image_url(img):
            potential_images.append(img)

    # Si pas d'image trouvée, faire le scraping immédiatement
    if not potential_images:
        image_url = process_entry_image(entry, image_cache)
    else:
        image_url = potential_images[0]
        
    entry.image_url = image_url
    entry.published_date = parse_date(entry)
    return entry

def fetch_rss_feed(url):
    logger.info(f"Fetching RSS feed from URL: {url}")
    feed = parse_feed_cached(url)
    entries = []
    
    for entry in feed.entries:
        image_url = None
        
        # Special handling for jeuxvideo.com images
        if 'jeuxvideo.com' in url:
            if hasattr(entry, 'enclosures') and entry.enclosures:
                for enclosure in entry.enclosures:
                    if enclosure.type and enclosure.type.startswith('image/'):
                        original_image_url = enclosure.get('url') or enclosure.get('href')
                        if original_image_url:
                            logger.info(f"Found JVC image in enclosure: {original_image_url}")
                            entry.image_from_enclosure = True
                            # Use the original URL for now, the actual upload will happen in process_image_url
                            image_url = original_image_url
                            break

        if not image_url:
            # Default image handling for other sources
            if hasattr(entry, 'enclosures') and entry.enclosures:
                for enclosure in entry.enclosures:
                    if enclosure.type and enclosure.type.startswith('image/'):
                        image_url = enclosure.get('url') or enclosure.get('href')
                        logger.info(f"Found image in enclosure: {image_url}")
                        break

            if not image_url:
                image_url = getattr(entry, 'image_url', None)
        
        entries.append({
            'title': entry.title,
            'link': entry.link,
            'summary': entry.summary,
            'published_date': parse_date(entry),
            'image_url': image_url,
            'is_jvc_enclosure': getattr(entry, 'image_from_enclosure', False)
        })
    
    logger.info(f"Finished fetching RSS feed from URL: {url}")
    return entries

def get_article_content(url):
    """Récupère le contenu complet d'un article et son image à la demande"""
    logger.info(f"Fetching article content for URL: {url}")
    content, scraped_image_url = get_full_article(url)
    
    # Ne pas écraser l'image JVC de l'enclosure
    if 'jeuxvideo.com' in url:
        # Rechercher l'entrée correspondante dans les articles déjà traités
        for entry in fetch_rss_feed("https://www.jeuxvideo.com/rss/rss.xml"):
            if entry['link'] == url and entry['is_jvc_enclosure']:
                logger.info(f"Using JVC enclosure image instead of scraped image: {entry['image_url']}")
                return {
                    'url': url,
                    'content': content,
                    'image_url': entry['image_url']
                }
    
    return {
        'url': url,
        'content': content,
        'image_url': scraped_image_url
    }

# Exemple d'utilisation
if __name__ == "__main__":
    url = "http://example.com/rss"
    entries = fetch_rss_feed(url)
    for entry in entries:
        print(entry['title'])
        print(entry['link'])
        print(entry['summary'])
        print(entry['image_url'])
        print(entry['published_date'])
        print()
    
    # Fetch content for a specific article on demand
    article_url = "https://www.fredzone.org/oshi-no-ko-les-createurs-saluent-ladaptation-en-live-action-malgre-les-craintes-initiales-ce-qui-arrive-rarement/"
    article_content = get_article_content(article_url)
    print(article_content)
