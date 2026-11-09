# Crave Retail Shopping Assistant

The React/Vite chat UI is in this directory. The FastAPI search service and
catalog ingestion script are in the repository root.

## Search and response flow

1. `rag_service.py` extracts the product phrase and any category, color, size,
   or price constraints from the latest request and recent conversation.
2. `shopping-assist.py` searches product titles with English full-text matching
   and applies category, audience (men, women, boys, girls, kids, babies,
   newborn, or unisex), color, size, and price constraints to the
   catalog fields. Numeric sizes use whole-value matching (size 10 does not
   match 10.5). pgvector ranks the resulting products by relevance.
3. If title matching finds nothing, the service retries with semantic ranking
   while keeping the requested audience, color, size, and price filters. These
   results are labeled as closest matches. If none satisfy the filters, the
   assistant explains which filters were applied and offers actions to remove a
   specific constraint. Interpreted filters are shown in the chat and sent with
   conversation history so follow-up refinements can retain the remaining scope.
4. Replies are generated locally from the search outcome, so each request needs
   only one LLM call for intent extraction.

Follow-ups include the previous assistant turn's product facts in the request,
so refinements can retain the product scope and compare prices. A "cheaper"
follow-up searches below the least expensive item in the previous results.

## Run locally

- Start the FastAPI service from the repository root with
  `./venv/bin/python shopping-assist.py`. It expects the configured PostgreSQL
  database and `products` table to be available, and `OPENAI_API_KEY` to be set.
- In this directory, run `npm run dev` to start the Vite UI.
- Run `npm run lint` and `npm run build` here to check the UI.
