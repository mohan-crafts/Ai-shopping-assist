import os
import json
import instructor
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import Optional

client = instructor.from_openai(OpenAI(api_key=os.environ.get("OPENAI_API_KEY")))

class ShoppingIntentResponse(BaseModel):
    is_vague: bool = Field(description="True only when the item or shopping intent is too broad to search usefully.")
    clarification_question: Optional[str] = Field(None, description="A brief question to clarify a vague request.")
    search_keyword: Optional[str] = Field(None, description="The core product phrase to match in product titles.")
    category: Optional[str] = Field(None, description="A catalog category constraint, when requested.")
    audience: Optional[str] = Field(
        None,
        description="Requested audience: men, women, boys, girls, kids, babies, newborn, or unisex.",
    )
    color: Optional[str] = Field(None, description="A requested product color.")
    size: Optional[str] = Field(None, description="A requested product size.")
    price_min: Optional[float] = Field(None, description="An explicit minimum price.")
    price_max: Optional[float] = Field(None, description="An explicit maximum price.")


def analyze_user_intent(query: str, conversation_history: Optional[list] = None) -> ShoppingIntentResponse:
    instructions = """
    Extract product search filters from the latest shopper message.
    Use the recent conversation, including previously returned product titles and prices,
    to understand follow-ups such as "only blue ones" and "anything cheaper".
    Carry forward the previous product/search scope and filters unless the shopper changes
    or removes them. A follow-up that changes a filter is not vague if its product scope
    is clear from the conversation. Mark a request vague only if there is not enough
    context to determine what kind of product to search for; provide one short
    clarification_question in that case.
    If the shopper explicitly asks to remove a filter (for example, "remove the size
    filter", "any color", or "no price limit"), clear that filter and retain the other
    filters and product scope from the conversation.

    Extract only constraints actually requested or clearly carried forward:
    - search_keyword: concise product phrase suitable for matching titles
    - category: category value/phrase from the catalog
    - audience: men, women, boys, girls, kids, babies, newborn, or unisex when requested
    - color, size: requested values
    - price_min, price_max: explicit numeric price bounds only
    Do not invent a price limit for "cheaper"; that comparison is handled against
    prices in the previous retrieved results.
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_model=ShoppingIntentResponse,
        messages=[
            {"role": "system", "content": instructions},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "recent_conversation": conversation_history[-6:] if conversation_history else [],
                        "latest_message": query,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        temperature=0.3,
    )
    return response