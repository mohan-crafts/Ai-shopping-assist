import json
import os
import re
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import psycopg2
from sentence_transformers import SentenceTransformer
from rag_service import analyze_user_intent
from typing import List, Optional

app = FastAPI(title="Crave Retail Search Service", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "database": os.getenv("DB_NAME", "crave_retail"),
    "user": os.getenv("DB_USER", "superadmin"),
    "password": os.getenv("DB_PASSWORD", "")
}

print("⏳ Loading embedding model into memory...")
model = SentenceTransformer('all-MiniLM-L6-v2')

class ProductContext(BaseModel):
    title: str
    category: Optional[str] = None
    audience: Optional[str] = None
    price: Optional[float] = None
    color: Optional[str] = None
    size: Optional[str] = None

class FilterContext(BaseModel):
    label: str
    value: str

class Message(BaseModel):
    role: str
    content: str
    products: List[ProductContext] = Field(default_factory=list)
    filters: List[FilterContext] = Field(default_factory=list)

class SearchRequest(BaseModel):
    query: str
    messages: List[Message] = Field(default_factory=list)
    limit: int = Field(default=5, ge=1, le=20)


def build_active_filters(intent_analysis, audience, price_max):
    filters = []
    if intent_analysis.search_keyword:
        filters.append({"label": "Product", "value": intent_analysis.search_keyword})
    if intent_analysis.category:
        filters.append({"label": "Category", "value": intent_analysis.category})
    if audience:
        filters.append({"label": "Audience", "value": audience.replace("_", " ")})
    if intent_analysis.color:
        filters.append({"label": "Color", "value": intent_analysis.color})
    if intent_analysis.size:
        filters.append({"label": "Size", "value": intent_analysis.size})
    if intent_analysis.price_min is not None:
        filters.append({"label": "Min price", "value": f"${intent_analysis.price_min:g}"})
    if price_max is not None:
        filters.append({"label": "Max price", "value": f"${price_max:g}"})
    return filters


def build_refinement_suggestions(intent_analysis, audience):
    product = intent_analysis.search_keyword or intent_analysis.category or "these products"
    suggestions = []
    if intent_analysis.size:
        suggestions.append(f"Remove the size filter and keep the rest of my {product} search")
    if intent_analysis.color:
        suggestions.append(f"Remove the color filter and keep the rest of my {product} search")
    if intent_analysis.price_min is not None or intent_analysis.price_max is not None:
        suggestions.append(f"Remove the price limit and keep the rest of my {product} search")
    if audience:
        suggestions.append(f"Remove the audience filter and keep the rest of my {product} search")
    if len(suggestions) < 3:
        suggestions.append(f"Show similar {product}")
    if len(suggestions) < 3:
        suggestions.append(f"Browse all {product}")
    return suggestions[:3]


def is_conversational_acknowledgement(query):
    normalized_query = re.sub(r"[^\w\s']", " ", query.casefold())
    normalized_query = re.sub(r"\s+", " ", normalized_query).strip()
    return bool(re.fullmatch(
        r"(?:thank you(?: so much)?|thanks(?: a lot| so much)?|thx|ty|"
        r"i appreciate it|much appreciated|you are welcome|you're welcome)",
        normalized_query,
    ))


def parse_budget_reply(query, messages):
    amount_match = re.fullmatch(
        r"\s*\$?\s*(\d+(?:\.\d{1,2})?)\s*(?:dollars?|usd)?\s*",
        query,
        re.IGNORECASE,
    )
    if not amount_match:
        return None

    previous_assistant = next(
        (message for message in reversed(messages) if message.role == "assistant"),
        None,
    )
    if not previous_assistant or not re.search(
        r"\b(?:price range|price limit|budget|how much|what price)\b",
        previous_assistant.content,
        re.IGNORECASE,
    ):
        return None
    return float(amount_match.group(1))


@app.post("/api/search")
def semantic_search(request: SearchRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Search query cannot be empty.")

    try:
        history_dicts = [
            {
                "role": message.role,
                "content": message.content,
                "products": [product.model_dump() for product in message.products],
                "filters": [active_filter.model_dump() for active_filter in message.filters],
            }
            for message in request.messages
        ]
        if is_conversational_acknowledgement(request.query):
            return {
                "query": request.query,
                "assistant_message": "You're welcome! Let me know if you'd like help finding or refining anything else.",
                "suggestions": [],
                "filters": [],
                "results": [],
                "match_type": "conversation",
            }

        budget_reply = parse_budget_reply(request.query, request.messages)
        intent_analysis = analyze_user_intent(request.query, history_dicts)
        if budget_reply is not None:
            intent_analysis = intent_analysis.model_copy(update={
                "is_vague": False,
                "price_min": None,
                "price_max": budget_reply,
            })

        if intent_analysis.is_vague:
            return {
                "query": request.query,
                "assistant_message": intent_analysis.clarification_question or "What kind of product are you looking for?",
                "suggestions": [],
                "filters": [],
                "results": []
            }

        audience_patterns = {
            "baby_boys": r"\b(?:baby|infant|newborn)[ -]?boys?\b",
            "baby_girls": r"\b(?:baby|infant|newborn)[ -]?girls?\b",
            "newborn": r"\bnewborns?\b",
            "babies": r"\b(?:bab(?:y|ies)|infants?)\b",
            "boys": r"\bboys?\b",
            "girls": r"\bgirls?\b",
            "kids": r"\b(?:kids?|children|child|toddlers?)\b",
            "men": r"\b(?:men|mens|male)\b",
            "women": r"\b(?:women|womens|woman|female)\b",
            "unisex": r"\bunisex\b",
        }
        explicit_audiences = [
            audience
            for audience, pattern in audience_patterns.items()
            if re.search(pattern, request.query, re.IGNORECASE)
        ]
        if any(audience in explicit_audiences for audience in ("baby_boys", "baby_girls")):
            explicit_audiences = [
                audience for audience in explicit_audiences
                if audience not in ("babies", "newborn", "boys", "girls")
            ]
        audience = (
            explicit_audiences[0]
            if len(explicit_audiences) == 1
            else intent_analysis.audience
        )

        cheaper_follow_up = bool(re.search(
            r"\b(cheaper|less expensive|more affordable|lower[- ]priced|lower price|costs? less)\b",
            request.query,
            re.IGNORECASE,
        ))
        price_max = intent_analysis.price_max
        if cheaper_follow_up:
            previous_results = next(
                (
                    message.products
                    for message in reversed(request.messages)
                    if message.role == "assistant" and message.products
                ),
                [],
            )
            previous_prices = [
                product.price
                for product in previous_results
                if product.price is not None
            ]
            if not previous_prices:
                return {
                    "query": request.query,
                    "assistant_message": "I couldn't determine the prices in the previous results. What price limit should I use?",
                    "suggestions": [],
                    "filters": [],
                    "results": [],
                }
            price_max = min(previous_prices) - 0.01

        # Embed the retained product scope and active facets, not just a terse follow-up.
        embedding_query = " ".join(
            value for value in (
                intent_analysis.search_keyword,
                intent_analysis.category,
                audience,
                intent_analysis.color,
                intent_analysis.size,
            ) if value
        ) or request.query
        embedding_list = model.encode(embedding_query).tolist()
        vector_str = "[" + ",".join(map(str, embedding_list)) + "]"

        filters = ["embedding IS NOT NULL"]
        filter_params = []
        if intent_analysis.category:
            category_pattern = f"%{intent_analysis.category.lower()}%"
            filters.append("""
                (
                    LOWER(category) LIKE %s
                    OR NOT EXISTS (
                        SELECT 1 FROM products AS category_option
                        WHERE LOWER(category_option.category) LIKE %s
                    )
                )
            """)
            filter_params.extend([category_pattern, category_pattern])
        if audience:
            audience_text = """regexp_replace(
                lower(concat_ws(' ',
                    title,
                    metadata ->> 'department',
                    metadata ->> 'gender',
                    metadata -> 'details' ->> 'Suggested Users'
                )),
                '[^a-z]+', ' ', 'g'
            )"""
            audience_patterns_sql = {
                "men": ("(^| )(men|mens|male)( |$)", "(^| )(women|womens|woman|female)( |$)"),
                "women": ("(^| )(women|womens|woman|female)( |$)", "(^| )(men|mens|male)( |$)"),
                "boys": ("(^| )(boys|boy)( |$)", "(^| )(girls|girl)( |$)"),
                "girls": ("(^| )(girls|girl)( |$)", "(^| )(boys|boy)( |$)"),
                "kids": ("(^| )(kids|kid|children|child|boys|boy|girls|girl|toddlers|toddler|infants|infant|babies|baby|newborns|newborn|unisex child|unisex baby)( |$)", None),
                "babies": ("(^| )(babies|baby|infants|infant)( |$)", None),
                "newborn": ("(^| )(newborns|newborn|infants|infant)( |$)", None),
                "baby_boys": ("(^| )baby boys( |$)", None),
                "baby_girls": ("(^| )baby girls( |$)", None),
                "unisex": ("(^| )unisex( |$)", None),
            }
            audience_pattern = audience_patterns_sql.get(audience)
            if audience_pattern:
                filters.append(f"{audience_text} ~ '{audience_pattern[0]}'")
                if audience_pattern[1]:
                    filters.append(f"{audience_text} !~ '{audience_pattern[1]}'")
        if intent_analysis.color:
            filters.append("LOWER(COALESCE(metadata ->> 'color', '')) LIKE %s")
            filter_params.append(f"%{intent_analysis.color.lower()}%")
        if intent_analysis.size:
            requested_size = intent_analysis.size.strip().lower()
            if re.fullmatch(r"\d+(?:\.\d+)?", requested_size):
                size_pattern = rf"(^|[^0-9.]){re.escape(requested_size)}([^0-9.]|$)"
                filters.append("LOWER(COALESCE(metadata ->> 'size', '')) ~ %s")
                filter_params.append(size_pattern)
            else:
                filters.append("LOWER(COALESCE(metadata ->> 'size', '')) LIKE %s")
                filter_params.append(f"%{requested_size}%")
        if intent_analysis.price_min is not None:
            filters.append("price >= %s")
            filter_params.append(intent_analysis.price_min)
        if price_max is not None:
            filters.append("price <= %s")
            filter_params.append(price_max)

        conn = psycopg2.connect(**DB_CONFIG)
        try:
            with conn.cursor() as cur:
                def fetch_rows(require_title_match):
                    query_filters = list(filters)
                    query_params = [vector_str, *filter_params]
                    if require_title_match and intent_analysis.search_keyword:
                        query_filters.append(
                            "to_tsvector('english', title) @@ plainto_tsquery('english', %s)"
                        )
                        query_params.append(intent_analysis.search_keyword)
                    query_params.append(request.limit)
                    cur.execute(f"""
                        SELECT product_id, title, category, price, rating, image_url, metadata, 
                               (embedding <=> %s::vector) AS distance
                        FROM products
                        WHERE {" AND ".join(query_filters)}
                        ORDER BY distance ASC
                        LIMIT %s;
                    """, query_params)
                    return cur.fetchall()

                rows = fetch_rows(require_title_match=True)
                used_semantic_fallback = False
                if not rows and intent_analysis.search_keyword:
                    rows = fetch_rows(require_title_match=False)
                    used_semantic_fallback = bool(rows)

                results = []
                for row in rows:
                    metadata = row[6] or {}
                    if isinstance(metadata, str):
                        metadata = json.loads(metadata)
                    results.append({
                        "product_id": row[0],
                        "title": row[1],
                        "category": row[2],
                        "price": float(row[3]) if row[3] is not None else None,
                        "rating": float(row[4]) if row[4] is not None else None,
                        "image_url": row[5],
                        "metadata": metadata,
                        "audience": audience,
                        "color": metadata.get("color"),
                        "size": metadata.get("size"),
                        "similarity_score": round(1.0 - float(row[7]), 4)
                    })
        finally:
            conn.close()

        if not results:
            active_filters = build_active_filters(intent_analysis, audience, price_max)
            filter_summary = ", ".join(
                f"{item['label'].lower()} {item['value']}" for item in active_filters
            )
            if not filter_summary:
                filter_summary = "those search details"
            return {
                "query": request.query,
                "assistant_message": (
                    f"I couldn't find catalog products matching {filter_summary}. "
                    "We can broaden the search—what would you like to change?"
                ),
                "suggestions": build_refinement_suggestions(intent_analysis, audience),
                "filters": active_filters,
                "results": [],
                "match_type": "none",
            }

        suggestions = ["Show lower-priced options"]
        if intent_analysis.size:
            suggestions.append("Try a different size")
        if intent_analysis.color:
            suggestions.append("Try a different color")
        if audience:
            suggestions.append("Show products for another audience")
        if len(suggestions) < 3:
            suggestions.extend(["Refine the product type", "Adjust the price range"])

        return {
            "query": request.query,
            "assistant_message": (
                f"I couldn't find an exact title match for “{request.query}”, "
                "but these are the closest catalog products I found that fit your "
                "other filters. Check each product's listed details."
                if used_semantic_fallback else
                f"I found {len(results)} product"
                f"{'' if len(results) == 1 else 's'} matching your request. "
                "Here are the most relevant options."
            ),
            "suggestions": suggestions[:4],
            "filters": build_active_filters(intent_analysis, audience, price_max),
            "results": results,
            "match_type": "similar" if used_semantic_fallback else "matched",
        }

    except Exception as e:
        print(f"❌ Search failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)