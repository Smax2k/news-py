import json
import os
from datetime import datetime
from bs4 import BeautifulSoup
import re

PROCESSED_ARTICLES_FILE = "processed_articles.json"

def load_processed_articles(file_path):
    """Charge la liste des articles déjà traités"""
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Conversion du format ancien (liste d'URLs) vers le nouveau format
                if isinstance(data, list):
                    return {"articles": [{"url": url} for url in data]}
                return data
        except:
            return {"articles": []}
    return {"articles": []}

def save_processed_articles(data, file_path):
    """Sauvegarde la liste des articles traités"""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)  # Ajout de ensure_ascii=False pour préserver les accents

def clean_article_content(content):
    """Nettoie le contenu d'un article des balises HTML et du texte indésirable"""
    if not content:
        return ""
    
    # Si c'est un objet BeautifulSoup ou Tag, obtenir le texte
    if hasattr(content, 'get_text'):
        try:
            content = content.get_text(separator=' ', strip=True)
        except:
            content = str(content)
    
    # Convertir en string si ce n'est pas déjà le cas
    content = str(content)
    
    # Nettoyer les balises HTML restantes
    content = re.sub(r'<[^>]+>', ' ', content)
    
    # Supprimer les contenus liés aux cookies et consentements
    patterns_to_remove = [
        r'Ce contenu est bloqué.*?Gérer mes choix',
        r'Les informations recueillies sont destinées.*?politique Cookies',
        r'En poursuivant votre navigation.*?cookies',
        r'Vous gardez la possibilité.*?tout moment',
    ]
    
    for pattern in patterns_to_remove:
        content = re.sub(pattern, '', content, flags=re.DOTALL)
    
    # Nettoyer les caractères spéciaux et espacements
    content = content.replace('\n', ' ')
    content = content.replace('\r', ' ')
    content = content.replace('\t', ' ')
    content = ' '.join(content.split())
    
    return content.strip()

def clean_analysis(analysis):
    """Nettoie et formate l'analyse"""
    if not analysis:
        return {}
        
    if isinstance(analysis, str):
        try:
            # Essayer de convertir la string JSON en dictionnaire
            analysis = json.loads(analysis)
        except json.JSONDecodeError:
            # Si échec, retourner un dictionnaire vide
            return {}
            
    # S'assurer que c'est un dictionnaire
    if not isinstance(analysis, dict):
        return {}
        
    return analysis

def format_date(date):
    """Formate la date en string ISO"""
    if not date:
        return None
        
    try:
        if isinstance(date, datetime):
            return date.isoformat()
        return str(date)
    except:
        return None

def clean_quotes(text):
    """Nettoie et normalise les guillemets dans le texte"""
    if not text:
        return ""
    
    # Remplacer tous les types de guillemets par des guillemets simples
    replacements = {
        '"': "'",  # guillemet droit double
        '"': "'",  # guillemet courbe gauche
        '"': "'",  # guillemet courbe droit
        '«': "'",  # guillemet français ouvrant
        '»': "'",  # guillemet français fermant
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    return text

def add_processed_article(url, title=None, content=None, analysis=None, date=None, image_url=None, source=None, notion_id=None, is_double=False):
    """Ajoute un article complet à la liste des traités avec formatage amélioré"""
    articles_data = load_processed_articles(PROCESSED_ARTICLES_FILE)
    
    # Nettoyer les guillemets du titre et du contenu
    title = clean_quotes(title) if title else ""
    content = clean_quotes(clean_article_content(content)) if content else ""
    
    article_data = {
        "url": url,
        "title": title,
        "content": content,
        "analysis": clean_analysis(analysis),
        "date": format_date(date),
        "image_url": image_url if image_url else "",
        "source": source if source else "",
        "processed_date": datetime.now().isoformat(),
        "notion_id": notion_id if notion_id else None
    }

    # Vérifier que notion_id est présent avant d'ajouter l'article    
    if notion_id:
        print(f"Ajout de l'article avec Notion ID: {notion_id}")
    else:
        print("Attention: Ajout de l'article sans Notion ID")

    # Supprimer les clés avec valeurs None/vides    
    article_data = {k:v for k,v in article_data.items() if v is not None and v != ""}
        
    articles_data["articles"].append(article_data)
    save_processed_articles(articles_data, PROCESSED_ARTICLES_FILE)

def is_article_processed(url):
    """Vérifie si un article a déjà été traité"""
    articles_data = load_processed_articles(PROCESSED_ARTICLES_FILE)
    return any(article.get("url") == url for article in articles_data["articles"])

def clear_processed_articles():
    """Supprime la liste des articles traités"""
    if os.path.exists(PROCESSED_ARTICLES_FILE):
        os.remove(PROCESSED_ARTICLES_FILE)
