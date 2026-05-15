"""LLM factory. Returns an OpenAI-compatible chat model wired to OpenRouter."""

import os

from langchain_openai import ChatOpenAI


def get_llm(temperature: float = 0.2) -> ChatOpenAI:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set — copy .env.example to .env")
        
    # Fallback to direct OpenAI model if no custom base URL is specified
    base_url = os.environ.get("LLM_BASE_URL")
    default_model = "openai/gpt-4o-mini" if base_url else "gpt-4o-mini"
    
    kwargs = {
        "model": os.environ.get("LLM_MODEL", default_model),
        "api_key": api_key,
        "temperature": temperature,
    }
    if base_url:
        kwargs["base_url"] = base_url
        
    return ChatOpenAI(**kwargs)
