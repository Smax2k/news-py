import os
from dotenv import load_dotenv
from rss_reader import fetch_rss_feed, get_article_content
from chatgpt_processor import process_with_chatgpt
from notion_integration import create_notion_page
from config import RSS_FEEDS
import json
from article_tracker import add_processed_article
from lock_manager import file_lock, LockError, is_cleaning_running
from notion_cleaner import load_processed_articles, delete_page
from image_handler import process_image_url

print("Début du script...")

load_dotenv()

# Charger et afficher le seuil de nettoyage automatique
auto_clean_threshold = int(os.getenv("AUTO_CLEAN_THRESHOLD", "400"))
print(f"Seuil de nettoyage automatique: {auto_clean_threshold} articles")

def clean_json_string(analysis):
    """Nettoie la chaîne JSON des balises markdown"""
    if isinstance(analysis, str):
        analysis = analysis.replace('```json', '').replace('```', '').strip()
    return analysis

def is_article_processed(url, processed_articles):
    """Vérifie si un article avec l'URL donnée a déjà été traité"""
    return any(article['url'] == url for article in processed_articles.get('articles', []))

def clean_old_articles(articles_data, number_to_remove=None):
    """Supprime les n plus anciens articles du fichier JSON et de Notion"""
    if number_to_remove is None:
        number_to_remove = int(os.getenv("CLEAN_REMOVE_COUNT", "100"))
    
    print(f"\nNettoyage des anciens articles...")
    print(f"Nombre d'articles à supprimer: {number_to_remove}")
    print(f"Nombre total d'articles avant nettoyage: {len(articles_data['articles'])}")
    
    # Trier les articles par date (du plus ancien au plus récent)
    articles_data['articles'].sort(key=lambda x: x.get('date', ''))
    
    # Articles à supprimer (les n premiers/plus anciens)
    articles_to_remove = articles_data['articles'][:number_to_remove]
    
    # Supprimer sur Notion
    for article in articles_to_remove:
        notion_id = article.get('notion_id')
        if notion_id:
            print(f"Suppression de la page Notion pour {article['title']}")
            if delete_page(notion_id):
                print("✓ Page Notion supprimée") 
            else:
                print("✗ Erreur lors de la suppression de la page Notion")
    
    # Supprimer du JSON
    articles_data['articles'] = articles_data['articles'][number_to_remove:]
    
    print(f"Nombre d'articles supprimés: {number_to_remove}")
    print(f"Nombre total d'articles après nettoyage: {len(articles_data['articles'])}")
    
    # Sauvegarder le fichier mis à jour
    with open('processed_articles.json', 'w') as f:
        json.dump(articles_data, f, indent=4)
    
    return articles_data

def process_new_articles():
    try:
        with file_lock(lock_type="main"):
            load_dotenv(override=True)
            
            print("Chargement des variables d'environnement...")
            api_key = os.getenv("OPENAI_API_KEY")
            max_articles_per_feed_raw = os.getenv("MAX_ARTICLES_PER_FEED", "3").strip().split('#')[0].strip()
            auto_clean_threshold = int(os.getenv("AUTO_CLEAN_THRESHOLD", "400"))
            try:
                max_articles_per_feed = int(max_articles_per_feed_raw)
            except ValueError:
                print(f"Erreur: MAX_ARTICLES_PER_FEED invalide ({max_articles_per_feed_raw}), utilisation de la valeur par défaut (3)")
                max_articles_per_feed = 3

            print(f"MAX_ARTICLES_PER_FEED configuré à: {max_articles_per_feed}")
            
            if is_cleaning_running():
                print("Le nettoyage de la base de données est en cours. Réessayez plus tard.")
                return False

            if not api_key:
                print("Erreur : OPENAI_API_KEY n'est pas définie.")
                return
            
            print("Début du traitement des flux RSS...")
            
            articles_data = load_processed_articles("processed_articles.json")
            print("\nDébug chargement articles:")
            print(f"Structure chargée: {type(articles_data)}")
            print(f"Nombre d'articles chargés: {len(articles_data.get('articles', []))}")
            
            for feed in RSS_FEEDS:
                rss_url = feed["url"]
                feed_name = feed["name"]
                print(f"Fetching feed from: {feed_name} ({rss_url})")
                entries = fetch_rss_feed(rss_url)
                print(f"Nombre total d'articles trouvés: {len(entries)}")
                entries = entries[:max_articles_per_feed]
                print(f"Nombre d'articles après limite: {len(entries)}")
                if not entries:
                    print(f"Aucun article trouvé pour le flux : {feed_name}")
                    continue
                for entry in entries:
                    if is_article_processed(entry['link'], articles_data):
                        print(f"Article déjà traité : {entry['link']}")
                        continue
                    
                    print("Flux:", feed_name)
                    print("Titre:", entry['title'])
                    print("Lien:", entry['link'])
                    
                    # Fetch content for the specific article on demand
                    article_content = get_article_content(entry['link'])
                    full_content = article_content['content']
                    
                    # Process image URL based on source
                    raw_image_url = article_content['image_url']
                    image_url = process_image_url(raw_image_url, feed["name"])
                    
                    content_to_use = full_content or entry['summary']
                    
                    if image_url:
                        print("Image:", image_url)
                    
                    published_date = entry['published_date']
                    if published_date:
                        print("Date:", published_date)
                    
                    # Analyser l'article avec ChatGPT
                    analysis = process_with_chatgpt(entry['title'], content_to_use, api_key, articles_data)
                    
                    print("Création de la page Notion")
                    
                    status_code, response = create_notion_page(
                        entry['title'], 
                        content_to_use,
                        analysis,  # Utiliser l'analyse de ChatGPT ici
                        image_url,
                        entry['link'],
                        published_date,
                        feed_name
                    )
                    
                    if status_code == 200:
                        # Récupérer l'ID de la page Notion créée
                        notion_id = response.get('id') if response else None
                        add_processed_article(
                            entry['link'],
                            title=entry['title'],
                            content=content_to_use,
                            analysis=analysis,  # Utiliser l'analyse de ChatGPT ici aussi
                            date=published_date,
                            image_url=image_url,
                            source=feed_name,
                            notion_id=notion_id  # Ajouter l'ID Notion ici
                        )
                        print(f"Article envoyé à Notion (ID: {notion_id}) et ajouté au suivi")
            
            # Déplacer le nettoyage ici, après avoir traité tous les nouveaux articles
            if len(articles_data.get('articles', [])) > auto_clean_threshold:
                articles_data = clean_old_articles(articles_data)
                
    except LockError:
        print("Un autre processus est en cours d'exécution. Réessayez plus tard.")
        return False

if __name__ == "__main__":
    print("Appel de la fonction main...")
    process_new_articles()
    print("Fin du script...")
