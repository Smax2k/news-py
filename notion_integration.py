import os
import json
import requests
from dotenv import load_dotenv
import base64
from io import BytesIO
from PIL import Image
import html
import re

load_dotenv()

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")

def check_notion_connection():
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    try:
        response = requests.get(
            f"{NOTION_API_URL}/databases/{NOTION_DATABASE_ID}",
            headers=headers
        )
        if response.status_code == 200:
            print("Connexion à Notion réussie!")
            return True
        else:
            print(f"Erreur de connexion à Notion: {response.status_code}")
            print(f"Message: {response.json().get('message', 'Pas de message d\'erreur')}")
            return False
    except Exception as e:
        print(f"Erreur lors de la vérification de la connexion: {str(e)}")
        return False

def is_valid_url(url):
    """Vérifie si l'URL est valide"""
    return url and isinstance(url, str) and url.strip() != "" and (url.startswith('http://') or url.startswith('https://'))

def truncate_text(text, max_length=2000):
    """Tronque le texte à la longueur maximale en respectant les mots"""
    if not text or len(text) <= max_length:
        return text
    return text[:max_length-3].rsplit(' ', 1)[0] + '...'

def split_content(text, max_length=2000):
    """Divise le contenu en blocs de texte respectant la limite de taille"""
    if not text:
        return []
        
    chunks = []
    words = text.split()
    current_chunk = []
    current_length = 0
    
    for word in words:
        word_length = len(word) + 1  # +1 pour l'espace
        if current_length + word_length > max_length:
            chunks.append(' '.join(current_chunk))
            current_chunk = [word]
            current_length = word_length
        else:
            current_chunk.append(word)
            current_length += word_length
            
    if current_chunk:
        chunks.append(' '.join(current_chunk))
        
    return chunks

def split_content_for_notion(text, max_chunk_size=1800):
    """Divise le contenu en morceaux plus petits pour Notion"""
    if not text:
        return []
    
    chunks = []
    current_chunk = []
    current_length = 0
    
    for word in text.split():
        word_len = len(word) + 1  # +1 pour l'espace
        if current_length + word_len > max_chunk_size:
            chunks.append(' '.join(current_chunk))
            current_chunk = [word]
            current_length = word_len
        else:
            current_chunk.append(word)
            current_length += word_len
    
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    
    # Limiter le nombre total de chunks pour éviter une requête trop grande
    if len(chunks) > 10:
        chunks = chunks[:10]
        chunks[-1] = chunks[-1] + "... (contenu tronqué)"
    
    return chunks

def optimize_image(img, max_size=(800, 800), quality=85):
    """Redimensionne et optimise une image"""
    # Redimensionner l'image en gardant les proportions
    img.thumbnail(max_size, Image.Resampling.LANCZOS)
    
    # Convertir en RGB si nécessaire (pour les images RGBA)
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
        
    # Sauvegarder avec compression
    buffer = BytesIO()
    img.save(buffer, format='JPEG', quality=quality, optimize=True)
    return buffer.getvalue()

def download_and_prepare_image(image_url):
    """Télécharge l'image et la prépare pour Notion"""
    try:
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()
        
        # Ouvrir l'image avec PIL
        img = Image.open(BytesIO(response.content))
        
        # Optimiser l'image
        img_data = optimize_image(img)
        
        # Encoder en base64
        encoded = base64.b64encode(img_data).decode()
        
        # Vérifier la taille finale
        size_kb = len(encoded) / 1024
        if size_kb > 500:  # Si toujours trop grand
            print(f"Image trop grande ({size_kb:.1f}KB), nouvelle tentative avec compression plus forte")
            img_data = optimize_image(img, max_size=(600, 600), quality=60)
            encoded = base64.b64encode(img_data).decode()
        
        return encoded
    except Exception as e:
        print(f"Erreur lors du téléchargement de l'image: {str(e)}")
        return None

def clean_text(text):
    """Nettoie le texte des caractères HTML encodés et autres caractères spéciaux"""
    if not text:
        return ""
    
    # Décode les entités HTML (comme &quot;, &#039;, etc.)
    text = html.unescape(text)
    
    # Nettoie les codes HTML numériques restants (comme &#0039;)
    text = re.sub(r'&#\d+;', "'", text)
    
    # Supprime les caractères de contrôle
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\t')
    
    return text.strip()

def create_notion_page(title, content, analysis, image_url=None, article_url=None, published_date=None, author=None, is_double=False):
    if not check_notion_connection():
        print("Impossible de se connecter à la base de données Notion")
        return None, None

    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    # Nettoyer le titre et le contenu
    clean_title = clean_text(title)
    clean_content = clean_text(content)

    # Diviser le contenu en morceaux plus petits
    content_chunks = split_content_for_notion(clean_content)

    # Parser l'analyse JSON si c'est une string et la reformater
    if isinstance(analysis, str):
        # Nettoyer les balises markdown
        analysis = analysis.replace('```json', '').replace('```', '').strip()
        try:
            analysis_dict = json.loads(analysis)
            # Reformater le JSON de manière plus lisible
            analysis_formatted = json.dumps(analysis_dict, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            analysis_dict = {
                "isCommercial": False,
                "significanceScore": 0.0,
                "summary": analysis,
                "tags": []
            }
            analysis_formatted = json.dumps(analysis_dict, indent=2, ensure_ascii=False)
    else:
        analysis_dict = analysis
        analysis_formatted = json.dumps(analysis_dict, indent=2, ensure_ascii=False)

    # Debug de la date
    print(f"Date reçue pour Notion: {published_date}")

    # Créer la page Notion avec la structure correcte des propriétés
    properties = {
        "Title": {
            "title": [{"text": {"content": clean_title}}]
        },
        "URL": {
            "type": "url",
            "url": article_url if is_valid_url(article_url) else None
        },
        "Flux": {
            "type": "multi_select",
            "multi_select": [{"name": author}] if author else []
        },
        "Date": {
            "type": "date",
            "date": {"start": published_date} if published_date else None
        },
        "Contenu": {
            "type": "rich_text",
            "rich_text": [
                {"text": {"content": chunk}} 
                for chunk in content_chunks
            ]
        },
        "Commercial": {
            "type": "checkbox",
            "checkbox": analysis_dict.get("isCommercial", False)
        },
        "Score": {
            "type": "number",
            "number": float(analysis_dict.get("significanceScore", 0.0))
        },
        "Résumé": {  # Utiliser directement le résumé de ChatGPT
            "type": "rich_text",
            "rich_text": [{"text": {"content": analysis_dict.get("summary", "")}}]
        },
        "Tags": {
            "type": "multi_select",
            "multi_select": [{"name": tag} for tag in analysis_dict.get("tags", [])]
        },
        "Double": {  # Nouvelle propriété
            "checkbox": analysis_dict.get("isDouble", False)  # Utiliser isDouble de l'analyse
        }
    }

    # Debug de la requête
    if published_date:
        print(f"Date incluse dans la requête Notion : {properties['Date']}")
    else:
        print("Aucune date n'a été incluse dans la requête Notion")

    # Ajouter l'image uniquement si l'URL est valide
    if is_valid_url(image_url):
        properties["Image"] = {
            "files": [
                {
                    "name": "image",
                    "type": "external",
                    "external": {
                        "url": image_url
                    }
                }
            ]
        }

    data = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": properties,
        "cover": {
            "type": "external",
            "external": {
                "url": image_url
            }
        } if is_valid_url(image_url) else None
    }

    try:
        response = requests.post(NOTION_API_URL + "/pages", headers=headers, json=data)
        if response.status_code == 200:
            # Ajouter l'ID de la page créée dans la réponse
            return response.status_code, {"id": response.json()["id"]}
        return response.status_code, response.json()
    except Exception as e:
        print(f"Erreur lors de l'envoi à Notion: {str(e)}")
        return None, None

# Exemple d'utilisation
if __name__ == "__main__":
    title = "Exemple de titre"
    content = "Voici un exemple de contenu d'article."
    analysis = '{"isCommercial": false, "significanceScore": 7.5, "summary": "Résumé de l\'article.", "tags": ["Technologie", "Innovation"]}'
    status_code, response = create_notion_page(title, content, analysis)
    print(f"Status: {status_code}")
    print(f"Response: {response}")
