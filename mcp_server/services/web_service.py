import httpx
import urllib.parse
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger("agent_orch.web_service")

async def fetch_web_content(url: str) -> dict:
    """Accesses the Internet and retrieves raw text details from a webpage."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, follow_redirects=True, timeout=10.0)
            response.raise_for_status()
            
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Decompose elements that don't represent semantic body content
        for s in soup(["script", "style", "nav", "footer", "header", "aside"]):
            s.decompose()
            
        title = soup.title.string.strip() if soup.title else "No Title"
        text = soup.get_text(separator=" ")
        
        # Clean spacing
        clean_text = " ".join(text.split())
        clean_text = clean_text[:5000]
        
        return {
            "url": url,
            "title": title,
            "content": clean_text
        }
    except Exception as e:
        logger.error(f"Error fetching url '{url}': {e}")
        return {
            "url": url,
            "title": "Error",
            "content": f"Failed to fetch content from URL: {str(e)}"
        }

async def search_web(query: str, max_results: int = 5) -> list[dict]:
    """Queries the internet search engine and returns search results."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, follow_redirects=True, timeout=10.0)
            if response.status_code != 200:
                logger.warning(f"DuckDuckGo search returned non-200 status: {response.status_code}")
                return [{"error": f"DuckDuckGo returned HTTP {response.status_code}. You are being rate-limited. DO NOT retry searching immediately. Answer using your existing knowledge or inform the user."}]
            response.raise_for_status()
            
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        
        for body in soup.find_all("div", class_="result__body")[:max_results]:
            title_a = body.find("a", class_="result__a")
            snippet_a = body.find("a", class_="result__snippet")
            
            if title_a:
                title = title_a.text.strip()
                raw_href = title_a.get("href", "")
                
                # Parse the target url redirect from uddg parameter
                parsed = urllib.parse.urlparse(raw_href)
                uddg_params = urllib.parse.parse_qs(parsed.query).get("uddg")
                actual_url = uddg_params[0] if uddg_params else raw_href
                
                snippet = snippet_a.text.strip() if snippet_a else ""
                results.append({
                    "title": title,
                    "url": actual_url,
                    "snippet": snippet
                })
        
        if not results:
            logger.warning("DuckDuckGo search returned 0 results. Might be blocking/rate-limiting.")
            return [{"error": "DuckDuckGo returned empty results. You are likely being rate-limited or blocked. DO NOT retry searching immediately."}]
            
        return results
    except Exception as e:
        logger.error(f"Error performing search for query '{query}': {e}")
        return [{"error": f"Failed to perform search: {str(e)}"}]
