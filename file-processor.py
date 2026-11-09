import os
import json
import numpy as np
import pandas as pd
import psycopg2
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "crave_retail")
DB_USER = os.getenv("DB_USER", "superadmin")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

# Path to your raw Amazon JSON file (update this to your actual file path)
JSON_FILE_PATH = "products.json" 

def main():
    print("🚀 Starting Crave Retail ETL Ingestion Pipeline...")

    # 1. Connect to PostgreSQL
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        conn.autocommit = False
        print("✅ Successfully connected to PostgreSQL (`crave_retail`)")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return

    # 2. Ensure pgvector extension and products table exist
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                product_id VARCHAR(50) PRIMARY KEY,
                title TEXT NOT NULL,
                category VARCHAR(100),
                price NUMERIC(10, 2),
                rating NUMERIC(3, 2),
                image_url TEXT,
                metadata JSONB,
                embedding VECTOR(384)
            );
        """)
        conn.commit()
    print("✅ Database schema and `products` table verified.")

    # 3. Load embedding model (all-MiniLM-L6-v2 generates 384-dim vectors efficiently)
    print("⏳ Loading local embedding model (SentenceTransformer)...")
    model = SentenceTransformer('all-MiniLM-L6-v2')

    # 4. Parse JSON File
    if not os.path.exists(JSON_FILE_PATH):
        print(f"⚠️ Warning: File '{JSON_FILE_PATH}' not found in current directory.")
        print("Please place your Amazon Fashion JSON file in this folder and update JSON_FILE_PATH.")
        return

    print(f"📂 Parsing JSON file: {JSON_FILE_PATH}...")
    with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)

    df = pd.DataFrame(raw_data)
    print(f"📊 Loaded {len(df)} raw records. Cleaning data...")

    # 5. Data Cleaning & Normalization
    # Handling messy fields, missing prices, and empty titles
    df['title'] = df['title'].fillna('Unknown Product').astype(str)
    df['price'] = pd.to_numeric(df['price'], errors='coerce')
    df['rating'] = pd.to_numeric(df['average_rating'], errors='coerce')
    df['category'] = df['main_category'].fillna('General').astype(str)

    def extract_image_url(images):
        if not isinstance(images, list):
            return ''
        for image in images:
            if isinstance(image, dict) and image.get('variant') == 'MAIN':
                return image.get('large') or image.get('hi_res') or image.get('thumb') or ''
        for image in images:
            if isinstance(image, dict):
                return image.get('large') or image.get('hi_res') or image.get('thumb') or ''
        return ''

    if 'image_url' in df.columns:
        df['image_url'] = df['image_url'].fillna('').astype(str)
    elif 'images' in df.columns:
        df['image_url'] = df['images'].map(extract_image_url)
    else:
        df['image_url'] = ''
    # Create a rich descriptive text field for vector embedding generation
    df['search_text'] = "Product: " + df['title'] + " | Category: " + df['category']

    print("🧠 Generating vector embeddings for catalog items...")
    embeddings = model.encode(df['search_text'].tolist(), show_progress_bar=True)

    # 6. Bulk Insert into PostgreSQL
    print("💾 Bulk inserting records into PostgreSQL...")
    register_vector(conn)

    def clean_json_value(val):
        """Recursively clean values so no NaN, NaT, or NA ever reaches json.dumps."""
        if val is None:
            return None
        
        # Guard against lists, tuples, and numpy arrays before running pd.isna
        if isinstance(val, (list, tuple, np.ndarray)):
            return [clean_json_value(item) for item in val]
            
        if isinstance(val, dict):
            return {str(k): clean_json_value(v) for k, v in val.items()}
            
        if isinstance(val, float):
            if np.isnan(val) or np.isinf(val):
                return None
            return val

        # Safe scalar check for pandas NA / NaN
        try:
            if pd.isna(val):
                return None
        except Exception:
            pass
            
        return val
    
    with conn.cursor() as cur:
        for idx, row in df.iterrows():
            product_id = row.get('product_id', f"prod_{idx}")
            title = row['title']
            category = row['category']
            price = None if pd.isna(row['price']) else row['price']
            rating = None if pd.isna(row['rating']) else row['rating']
            image_url = row['image_url']
            # Clean row data: replace NaN/NaT/None with None so json.dumps produces valid JSON (null)
            row_dict = row.to_dict()
            
            clean_dict  = {k: clean_json_value(v) for k, v in row_dict.items()}
            
            # allow_nan=False guarantees Python will throw an error immediately if any NaN remains
            metadata = json.dumps(clean_dict, allow_nan=False)
            
            vector_embedding = embeddings[idx].tolist()

            cur.execute("""
                INSERT INTO products (product_id, title, category, price, rating, image_url, metadata, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (product_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    category = EXCLUDED.category,
                    price = EXCLUDED.price,
                    rating = EXCLUDED.rating,
                    image_url = EXCLUDED.image_url,
                    metadata = EXCLUDED.metadata,
                    embedding = EXCLUDED.embedding;
            """, (product_id, title, category, price, rating, image_url, metadata, vector_embedding))

        conn.commit()
    
    conn.close()
    print("🎉 ETL Ingestion Completed Successfully! Catalog is now live in PostgreSQL with vector embeddings.")

if __name__ == "__main__":
    main()