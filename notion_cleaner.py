import os
import requests
from dotenv import load_dotenv
import time
import json
from lock_manager import file_lock, LockError, is_main_running
import glob  # Ajouter cet import pour la gestion des fichiers

load_dotenv()

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")

def get_database_pages():
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    url = f"{NOTION_API_URL}/databases/{NOTION_DATABASE_ID}/query"
    
    pages = []
    has_more = True
    next_cursor = None
    
    while has_more:
        body = {}
        if next_cursor:
            body["start_cursor"] = next_cursor
            
        response = requests.post(url, headers=headers, json=body)
        data = response.json()
        
        if response.status_code != 200:
            print(f"Erreur lors de la récupération des pages: {response.status_code}")
            print(f"Message: {data.get('message')}")
            break
            
        pages.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        next_cursor = data.get("next_cursor")
        
    return pages

def delete_page(page_id):
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    url = f"{NOTION_API_URL}/pages/{page_id}"
    
    # Au lieu de DELETE, on utilise PATCH pour archiver la page
    data = {
        "archived": True
    }
    
    response = requests.patch(url, headers=headers, json=data)
    
    if response.status_code != 200:
        print(f"Erreur d'archivage: {response.status_code}")
        print(f"Détails: {response.text}")
        
    return response.status_code == 200

def get_page_url(page):
    """Récupère l'URL de la page depuis ses propriétés"""
    try:
        return page.get("properties", {}).get("URL", {}).get("url", None)
    except:
        return None

def load_processed_articles(filepath="processed_articles.json"):
    try:
        with open(filepath, 'r') as f:
            processed_articles = json.load(f)
            # Si c'est une liste (ancien format), convertir en dictionnaire
            if isinstance(processed_articles, list):
                return {"articles": processed_articles}
            return processed_articles
    except FileNotFoundError:
        return {"articles": []}

def save_processed_articles(data, filepath="processed_articles.json"):
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

def remove_article_by_url(articles_data, url):
    """Supprime un article du fichier JSON par son URL"""
    articles_data["articles"] = [
        article for article in articles_data["articles"] 
        if article["url"] != url
    ]
    return articles_data

def clean_log_files():
    """Nettoie les fichiers de logs ChatGPT"""
    try:
        log_files = glob.glob('logs/chatgpt_prompts_*.log')
        count = 0
        for file in log_files:
            try:
                os.remove(file)
                count += 1
                print(f"✓ Fichier log supprimé : {file}")
            except Exception as e:
                print(f"✗ Erreur lors de la suppression du fichier {file}: {e}")
        return count
    except Exception as e:
        print(f"Erreur lors du nettoyage des logs: {e}")
        return 0

def clean_database():
    try:
        if is_main_running():
            print("Le processus principal est en cours d'exécution. Réessayez plus tard.")
            return

        with file_lock(lock_type="process"):
            print("Verrou acquis. Début du nettoyage...")
            
            # Nettoyage des logs ChatGPT
            print("\nNettoyage des logs ChatGPT...")
            logs_deleted = clean_log_files()
            print(f"Nombre de fichiers logs supprimés : {logs_deleted}")
            
            print("\nNettoyage de la base de données Notion...")
            print("Récupération des pages de la base de données...")
            pages = get_database_pages()
            
            if not pages:
                print("Erreur: Impossible de récupérer les pages de la base de données ou base vide")
                return
                
            total_pages = len(pages)
            print(f"Nombre de pages à supprimer : {total_pages}")
            
            if total_pages == 0:
                print("Aucune page trouvée dans la base de données.")
                return
            
            # Charger la liste des articles traités
            articles_data = load_processed_articles()
            deleted_count = 0
            errors_count = 0
            
            for i, page in enumerate(pages, 1):
                try:
                    page_id = page.get("id")
                    if not page_id:
                        print(f"Page {i} invalide: ID manquant")
                        errors_count += 1
                        continue
                        
                    properties = page.get("properties", {})
                    title_info = properties.get("Title", {}).get("title", [{}])
                    title = title_info[0].get("text", {}).get("content", "Sans titre") if title_info else "Sans titre"
                    url = get_page_url(page)

                    print(f"Suppression de la page {i}/{total_pages}: {title}")
                    
                    if delete_page(page_id):
                        print(f"✓ Page supprimée avec succès")
                        if url:
                            # Mettre à jour le fichier JSON après chaque suppression réussie
                            articles_data = remove_article_by_url(articles_data, url)
                            try:
                                save_processed_articles(articles_data)
                                deleted_count += 1
                                print(f"✓ Article supprimé du fichier JSON")
                            except Exception as e:
                                print(f"✗ Erreur lors de la sauvegarde du fichier JSON : {str(e)}")
                                errors_count += 1
                    else:
                        print(f"✗ Erreur lors de la suppression de la page {page_id}")
                        errors_count += 1
                        
                    time.sleep(0.5)  # Anti rate-limit
                    
                except Exception as e:
                    print(f"Erreur lors du traitement de la page {i}: {str(e)}")
                    errors_count += 1
                    continue
            
            print("\nNettoyage terminé!")
            print(f"Pages Notion supprimées : {total_pages}")
            print(f"Articles supprimés du JSON : {deleted_count}")
            print(f"Fichiers logs supprimés : {logs_deleted}")
            print(f"Erreurs rencontrées : {errors_count}")

    except LockError:
        print("Un autre processus est en cours d'exécution. Réessayez plus tard.")
    except Exception as e:
        print(f"Une erreur s'est produite: {e}")
        # S'assurer que le verrou est libéré en cas d'erreur
        if os.path.exists('process.lock'):
            os.remove('process.lock')

if __name__ == "__main__":
    clean_database()
