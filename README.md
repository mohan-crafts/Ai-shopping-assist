# Retail Shopping Assistant

A chat UI for searching the Amazon Fashion product catalog.

## Flow

1. The React app sends the shopper's message and conversation history to FastAPI.
2. The Python service uses OpenAI to extract product type and filters such as
   audience, size, color, and budget.
3. PostgreSQL applies the filters and pgvector ranks matching products.
4. The UI shows real catalog products and their available details. Successful
   search replies are currently generated locally, not by an LLM.

## Tools

- **Frontend:** React, Vite
- **API and ingestion:** Python, FastAPI, pandas
- **Database and retrieval:** PostgreSQL, pgvector
- **AI:** OpenAI via Instructor for intent extraction; Sentence Transformers
  (`all-MiniLM-L6-v2`) for product and query embeddings

## Run locally

1. Copy `.env.example` to `.env`, fill in your local credentials, and load them
   in each terminal (the application does not load `.env` automatically):
   `set -a; source .env; set +a`
2. Start PostgreSQL with pgvector enabled and ingest the catalog once:
   `./venv/bin/python file-processor.py`
3. Start the API:
   `./venv/bin/python shopping-assist.py`
4. Start the frontend in another terminal:
   `cd shopping-assist && npm run dev`

The API expects a `products` table populated by the ingestion script. Optional
`DB_HOST`, `DB_PORT`, `DB_NAME`, and `DB_USER` environment variables override
the local defaults. The included `products.json` is a deterministic sample of
19,917 catalog records (half of the original 39,834) to keep the repository
under GitHub's per-file size limit. The complete source catalog is kept locally
as `products.full.json` and is excluded from Git.
