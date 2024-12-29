from openai import OpenAI
import os
from dotenv import load_dotenv
import hashlib
import json
from datetime import datetime
from article_tracker import clean_article_content  # Ajouter cet import
import logging
import tiktoken

load_dotenv()

# Configuration du logging
def setup_chatgpt_logger():
    logger = logging.getLogger('chatgpt_prompts')
    logger.setLevel(logging.INFO)
    
    # Important: supprimer les handlers existants
    logger.handlers = []
    
    # Vérifier si le logging est activé
    enable_logs = os.getenv("ENABLE_CHATGPT_LOGS", "false").lower() == "true"
    
    if not enable_logs:
        logger.addHandler(logging.NullHandler())
        return logger
    
    # Créer le dossier logs s'il n'existe pas
    os.makedirs('logs', exist_ok=True)
    
    # Configurer le handler pour écrire dans un fichier uniquement
    log_file = f"logs/chatgpt_prompts_{datetime.now().strftime('%Y%m%d')}.log"
    handler = logging.FileHandler(log_file, encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    # Désactiver la propagation des logs vers la console
    logger.propagate = False
    
    return logger

chatgpt_logger = setup_chatgpt_logger()

def log_chatgpt_interaction(prompt, response):
    """Log l'interaction avec ChatGPT"""
    if os.getenv("ENABLE_CHATGPT_LOGS", "false").lower() == "true":
        log_entry = f"""
=== NOUVELLE INTERACTION ===
PROMPT:
{prompt}

RÉPONSE:
{response}

{"="*50}
"""
        chatgpt_logger.info(log_entry)
        # Force le flush du logger
        for handler in chatgpt_logger.handlers:
            handler.flush()

def clean_chatgpt_response(response):
    """Nettoie la réponse de ChatGPT pour obtenir un JSON valide"""
    try:
        # Si c'est déjà un dictionnaire, le retourner tel quel
        if isinstance(response, dict):
            return response

        # Si c'est une chaîne, nettoyer et parser
        if isinstance(response, str):
            # Enlever les marqueurs de code markdown
            response = response.replace('```json', '').replace('```', '').strip()
            
            # Tenter de parser le JSON
            return json.loads(response)
    except json.JSONDecodeError as e:
        print(f"Erreur de décodage JSON: {e}")
        # Retourner un JSON par défaut en cas d'erreur
        return {
            "title": "Erreur de traitement",
            "summary": "Impossible d'analyser la réponse",
            "tags": [],
            "category": "undefined"
        }

def count_tokens(text, model="gpt-4"):
    """Compte le nombre de tokens dans un texte"""
    try:
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except Exception as e:
        print(f"Erreur lors du comptage des tokens: {e}")
        return 0

def process_with_chatgpt(title, content, api_key, articles_data=None):
    try:
        client = OpenAI(api_key=api_key)
        model = os.getenv("OPENAI_MODEL", "gpt-4")
        
        print("\nDébut préparation articles de comparaison...")
        
        # Charger directement depuis le fichier processed_articles.json
        try:
            with open("processed_articles.json", 'r', encoding='utf-8') as f:
                processed_data = json.load(f)
                articles = processed_data.get("articles", [])
                print(f"Nombre total d'articles trouvés dans processed_articles.json : {len(articles)}")
        except FileNotFoundError:
            articles = []
            print("Fichier processed_articles.json non trouvé")
        except json.JSONDecodeError:
            articles = []
            print("Erreur de lecture du fichier processed_articles.json")
        
        # Construire le texte de comparaison
        comparison_text = ""
        if articles:
            comparison_text = "\n=== Articles précédents ===\n"
            for i, article in enumerate(articles, 1):
                article_title = article.get('title', 'Sans titre')
                comparison_text += f"{i}. {article_title}\n"
        
        #print(comparison_text)

        prompt = f"""
        Tu es un assistant spécialisé dans l'analyse d'articles d'actualité. 
        Tu réponds uniquement au format JSON demandé.

        === Article à analyser ===
        TITRE: {title}
        CONTENU: {content[:1500]}

        {comparison_text}

        === Critères d'analyse ===
        1. SIMILARITÉ
        - Vérifier si l'article est similaire à un des articles récents listés
        - Un article est considéré comme similaire s'il traite du même sujet principal
        - Prendre en compte le titre et le contenu

        2. CONTENU COMMERCIAL
        - Mots promotionnels: "promo", "promotion", "offre", "soldes", "réduction"
        - Symboles monétaires et pourcentages
        - Mentions commerciales
        - Références temporelles
        - VPN et abonnements

        3. IMPORTANCE DE L'ARTICLE (0.0 à 10.0)
        4. RÉSUMÉ (factuel, très détaillés et précis)
        5. TAG principal (1 tag en français, commençant par une majuscule)

        Répondre EXACTEMENT dans ce format JSON:
        {{
          "isDouble": true/false,
          "similarArticle": "titre de l'article similaire ou null",
          "similarityReason": "explication courte de la similarité ou null",
          "isCommercial": true/false,
          "significanceScore": <nombre entre 0.0 et 10.0>,
          "summary": "<résumé en français>",
          "tags": ["tag1"]
        }}
        """
        
        # Compter les tokens du prompt
        token_count = count_tokens(prompt, model)
        print(f"\nNombre de tokens utilisés pour ce prompt: {token_count}")
        
        print("\nPrompt préparé, envoi à ChatGPT...")
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Tu es un assistant spécialisé dans l'analyse d'articles d'actualité."},
                {"role": "user", "content": prompt}
            ]
        )
        
        result = clean_chatgpt_response(response.choices[0].message.content)
        
        # Log de la réponse avec le nombre de tokens
        log_entry = f"Tokens utilisés: {token_count}\n\n"
        log_chatgpt_interaction(log_entry + prompt, json.dumps(result, indent=2, ensure_ascii=False))
        
        print(f"\nRésultat ChatGPT:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return json.dumps(result)
        
    except Exception as e:
        # Log de l'erreur
        log_chatgpt_interaction(prompt, f"ERREUR: {str(e)}")
        print(f"Erreur lors du traitement ChatGPT: {e}")
        return json.dumps({
            "isDouble": False,
            "similarArticle": null,
            "similarityReason": null,
            "isCommercial": false,
            "significanceScore": 5.0,
            "summary": "Erreur lors de l'analyse",
            "tags": []
        })

def generate_topic_id(title, content):
    """Génère un identifiant unique pour le sujet principal de l'article"""
    text = f"{title} {content}"
    return hashlib.md5(text.encode()).hexdigest()

def load_processed_articles(filepath):
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"articles": []}

def save_processed_articles(articles, filepath):
    with open(filepath, 'w') as f:
        json.dump(articles, f, indent=2)

def process_article(url, title, content, api_key, articles_data):
    # Nettoyer le contenu avant traitement
    clean_title = clean_article_content(title)
    clean_content = clean_article_content(content)
    
    # Analyse l'article avec ChatGPT
    analysis = process_with_chatgpt(clean_title, clean_content, api_key, articles_data)
    analysis_dict = json.loads(analysis)
    
    # Crée l'entrée pour l'article
    article_entry = {
        "url": url,
        "title": title,
        "content": content,
        "date": datetime.now().isoformat(),
        "analysis": analysis_dict,
        "isDouble": analysis_dict.get("isDouble", False),
        "similarArticle": analysis_dict.get("similarArticle"),
        "similarityReason": analysis_dict.get("similarityReason")
    }
    
    return article_entry

# Exemple d'utilisation
if __name__ == "__main__":
    api_key = os.getenv("OPENAI_API_KEY")
    filepath = "processed_articles.json"
    
    # Exemple d'utilisation
    articles_data = load_processed_articles(filepath)
    new_article = process_article(
        "https://example.com/article",
        "Titre test",
        "Contenu test",
        api_key,
        articles_data
    )
    articles_data["articles"].append(new_article)
    save_processed_articles(articles_data, filepath)
