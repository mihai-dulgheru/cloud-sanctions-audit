"""
FastAPI Backend for Sanctions Screening PoC.
Integrates EU Sanctions Map, UN Security Council, and AI analysis.
All evidence stored statelessly in DigitalOcean Spaces.
"""

import json
import os
import urllib.parse
from contextlib import asynccontextmanager
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Optional, Any

import httpx
import xmltodict
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from playwright.sync_api import sync_playwright
from pydantic import BaseModel

from storage import (upload_to_spaces, get_presigned_url, generate_audit_folder_path)

load_dotenv()

# Constants
EU_SANCTIONS_AUTOCOMPLETE_URL = "https://www.sanctionsmap.eu/api/v1/autocomplete/search"
EU_SANCTIONS_REGIME_URL = "https://www.sanctionsmap.eu/api/v1/regime"
EU_SANCTIONS_BASE_URL = "https://www.sanctionsmap.eu"
UN_CONSOLIDATED_URL = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"

LOCAL_CACHE_DIR = Path(__file__).parent / "cache"
UN_XML_LOCAL_PATH = LOCAL_CACHE_DIR / "consolidated.xml"
UN_XML_DATE_FILE = LOCAL_CACHE_DIR / "consolidated_date.txt"

UN_XML_SPACES_KEY = "cache/consolidated.xml"

_un_xml_cache: Optional[bytes] = None


# ============== Lifecycle Management ==============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handle application startup and shutdown events.
    Downloads/Loads UN XML data on startup.
    """
    global _un_xml_cache
    try:
        _un_xml_cache = await ensure_un_xml_cached()
        print("UN XML ready for sanctions screening")
    except Exception as e:
        print(f"Warning: Failed to download UN XML on startup: {e}")

    yield
    pass


app = FastAPI(title="Sanctions Screening API",
              description="Production-ready sanctions screening with EU and UN data sources", version="1.0.0",
              lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"],
                   allow_headers=["*"])


class SearchRequest(BaseModel):
    name: str
    search_type: str = "person"


class SearchResult(BaseModel):
    query: str
    search_type: str
    eu_found: bool
    eu_matches: list
    un_found: bool
    un_matches: list
    risk_score: Optional[str]
    ai_summary: Optional[str]
    evidence_urls: dict
    audit_folder: str


# ============== UN XML Cache Management ==============

async def download_un_xml() -> bytes:
    """Download fresh UN consolidated XML."""
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        response = await client.get(UN_CONSOLIDATED_URL)
        response.raise_for_status()
        return response.content


def get_cached_un_xml_date() -> Optional[date]:
    """Get the date when the UN XML was last downloaded."""
    if UN_XML_DATE_FILE.exists():
        try:
            date_str = UN_XML_DATE_FILE.read_text().strip()
            return date.fromisoformat(date_str)
        except Exception:
            return None
    return None


def save_un_xml_locally(content: bytes):
    """Save UN XML to local cache."""
    LOCAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    UN_XML_LOCAL_PATH.write_bytes(content)
    UN_XML_DATE_FILE.write_text(date.today().isoformat())
    print(f"UN XML cached locally: {UN_XML_LOCAL_PATH}")


def load_un_xml_locally() -> Optional[bytes]:
    """Load UN XML from local cache."""
    if UN_XML_LOCAL_PATH.exists():
        return UN_XML_LOCAL_PATH.read_bytes()
    return None


async def ensure_un_xml_cached() -> bytes:
    """
    Ensure UN XML is cached locally (downloaded today).
    If not downloaded today, delete old and download fresh.
    Also sync to DO Spaces.
    """
    today = date.today()
    cached_date = get_cached_un_xml_date()

    if cached_date == today:
        local_content = load_un_xml_locally()
        if local_content:
            print(f"Using locally cached UN XML from {cached_date}")
            return local_content

    if UN_XML_LOCAL_PATH.exists():
        print(f"Deleting old UN XML cache from {cached_date}")
        UN_XML_LOCAL_PATH.unlink()
    if UN_XML_DATE_FILE.exists():
        UN_XML_DATE_FILE.unlink()

    print("Downloading fresh UN consolidated XML...")
    xml_content = await download_un_xml()

    save_un_xml_locally(xml_content)

    try:
        upload_to_spaces(xml_content, UN_XML_SPACES_KEY, "application/xml")
        print(f"UN XML synced to Spaces: {UN_XML_SPACES_KEY}")
    except Exception as e:
        print(f"Warning: Failed to sync UN XML to Spaces: {e}")

    return xml_content


def get_un_xml() -> Optional[bytes]:
    """Get the cached UN XML content."""
    global _un_xml_cache
    if _un_xml_cache:
        return _un_xml_cache
    return load_un_xml_locally()


# ============== EU Sanctions Integration ==============

EU_HEADERS = {"Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9",
              "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
              "Referer": "https://www.sanctionsmap.eu/",
              "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"', "sec-ch-ua-mobile": "?0",
              "sec-ch-ua-platform": '"Windows"', }


async def search_eu_autocomplete(name: str) -> list:
    """Query EU Sanctions Map autocomplete API."""
    async with httpx.AsyncClient(timeout=30.0, headers=EU_HEADERS) as client:
        try:
            response = await client.get(EU_SANCTIONS_AUTOCOMPLETE_URL,
                                        params={"lang": "en", "search": name, "search_type": 1, "limit": 15})
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except Exception as e:
            print(f"EU Autocomplete API error: {e}")
            return []


async def search_eu_regime(name: str) -> list:
    """Query EU Sanctions Map regime API for detailed results."""
    async with httpx.AsyncClient(timeout=30.0, headers=EU_HEADERS) as client:
        try:
            response = await client.get(EU_SANCTIONS_REGIME_URL,
                                        params={"lang": "en", "search": name, "search_type": 1})
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except Exception as e:
            print(f"EU Regime API error: {e}")
            return []


async def search_eu_sanctions(name: str) -> dict:
    """Full EU sanctions search: autocomplete + regime details."""
    autocomplete_matches = await search_eu_autocomplete(name)

    name_lower = name.lower()
    name_found_in_autocomplete = any(
        name_lower in match.lower() or match.lower() in name_lower for match in autocomplete_matches)

    regime_matches = []
    if name_found_in_autocomplete:
        regime_matches = await search_eu_regime(name)

    return {"autocomplete": autocomplete_matches, "regimes": regime_matches, "found": name_found_in_autocomplete}


def _take_screenshot_as_pdf_sync(url: str, wait_time: int = 5000, wait_for_selector: str = None) -> bytes:
    """Take a screenshot of a page using Playwright (sync) and return as PDF."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Using dict for viewport is standard in python playwright, ignoring strict type warning is safe here
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        try:
            page.goto(url, wait_until="networkidle", timeout=60000)

            if wait_for_selector:
                try:
                    page.wait_for_selector(wait_for_selector, timeout=15000)
                except Exception:
                    pass

            page.wait_for_timeout(wait_time)

            pdf_bytes = page.pdf(format="A4", landscape=True, print_background=True,
                                 margin={"top": "20px", "right": "20px", "bottom": "20px", "left": "20px"})
            return pdf_bytes
        finally:
            browser.close()


def _take_eu_sanctions_screenshot_sync(query: str) -> bytes:
    """Take a screenshot of EU Sanctions Map with the search query."""
    search_obj = {"value": query, "searchType": {"id": 1, "title": "regimes, persons, entities"}}
    search_json = json.dumps(search_obj, separators=(',', ':'))
    encoded_search = urllib.parse.quote(search_json, safe='')
    url = f"https://www.sanctionsmap.eu/#/main?search={encoded_search}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(3000)
            page.wait_for_timeout(5000)

            page.evaluate("window.scrollBy(0, 200)")
            page.wait_for_timeout(1000)

            header_template = '''
                <div style="font-size: 10px; width: 100%; text-align: center; color: #666;">
                    <span class="date"></span>
                    <span style="margin-left: 20px;">EU Sanctions Map</span>
                </div>
            '''
            footer_template = '''
                <div style="font-size: 9px; width: 100%; padding: 0 20px; display: flex; justify-content: space-between; color: #666;">
                    <span class="url"></span>
                    <span><span class="pageNumber"></span>/<span class="totalPages"></span></span>
                </div>
            '''

            pdf_bytes = page.pdf(format="A4", landscape=True, print_background=True, display_header_footer=True,
                                 header_template=header_template, footer_template=footer_template,
                                 margin={"top": "40px", "right": "20px", "bottom": "40px", "left": "20px"})
            return pdf_bytes
        finally:
            browser.close()


async def take_screenshot_as_pdf(url: str, wait_time: int = 5000, wait_for_selector: str = None) -> bytes:
    """Async wrapper that runs sync Playwright in a thread pool."""
    import asyncio

    loop = asyncio.get_running_loop()
    # Pass arguments directly to run_in_executor to avoid partial/args linter warnings
    return await loop.run_in_executor(None, _take_screenshot_as_pdf_sync, url, wait_time, wait_for_selector)


async def take_eu_sanctions_screenshot(query: str) -> bytes:
    """Async wrapper for EU Sanctions Map screenshot."""
    import asyncio

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _take_eu_sanctions_screenshot_sync, query)


# ============== UN Security Council Integration ==============

def _ensure_list(data: Any) -> list:
    """Helper to ensure xmltodict data is always a list."""
    if data is None:
        return []
    if isinstance(data, list):
        return data
    return [data]


def _process_un_entry(entry: dict, query_parts: list[str], is_person: bool) -> Optional[dict]:
    """Helper to process a single UN entry (Individual or Entity) and check for matches using token logic."""

    if is_person:
        first = (entry.get("FIRST_NAME") or "").strip()
        second = (entry.get("SECOND_NAME") or "").strip()
        third = (entry.get("THIRD_NAME") or "").strip()
        fourth = (entry.get("FOURTH_NAME") or "").strip()

        # Construct full name from parts
        name_parts = [n for n in [first, second, third, fourth] if n]
        full_name = " ".join(name_parts)

        alias_key = "INDIVIDUAL_ALIAS"
        display_name = full_name.title()

        # We will check against the full name
        names_to_check = [full_name]
    else:
        entity_name = (entry.get("FIRST_NAME") or "").strip()
        alias_key = "ENTITY_ALIAS"
        # Preserve original case for entities if it looks like an acronym (all caps), otherwise title case
        display_name = entity_name.title() if entity_name.isupper() and len(entity_name) > 4 else entity_name
        names_to_check = [entity_name]

    # Collect aliases
    aliases = _ensure_list(entry.get(alias_key))
    alias_names = []
    for alias in aliases:
        a_name = (alias.get("ALIAS_NAME") or "").strip()
        if a_name:
            alias_names.append(a_name)

    # Combine all potential targets (Main Name + Aliases)
    targets = names_to_check + alias_names

    is_match = False
    matched_target = None

    # Check matches: ALL query parts must appear in at least ONE of the target strings
    # This allows for order independence (e.g. "Chaudhry Aamir" matching "Aamir Ali Chaudhry")
    # and partial matching
    for target in targets:
        target_lower = target.lower()

        # Verify if all parts of the user query exist in this specific target string
        # e.g. query "Aamir Chaudhry" -> parts ["aamir", "chaudhry"]
        # target "Aamir Ali Chaudhry" -> contains both "aamir" and "chaudhry"
        if all(part in target_lower for part in query_parts):
            is_match = True
            matched_target = target
            break

    if not is_match:
        return None

    # Update display name if it was only an alias match to show context
    if matched_target:
        # Check if the matched name is substantially different from the main display name
        if matched_target.lower() != display_name.lower() and matched_target.lower() not in display_name.lower():
            display_name = f"{display_name} (alias: {matched_target})"

    return {"dataid": entry.get("DATAID"), "name": display_name, "un_list_type": entry.get("UN_LIST_TYPE"),
            "reference_number": entry.get("REFERENCE_NUMBER"), "listed_on": entry.get("LISTED_ON"),
            "comments": (entry.get("COMMENTS1") or "")[:500]}


def search_un_sanctions(xml_content: bytes, name: str, search_type: str) -> list:
    """Parse UN XML and search for matching entries."""
    matches = []
    if not xml_content:
        return matches

    # Split query into parts for token-based matching (order independent)
    query_parts = name.lower().strip().split()
    if not query_parts:
        return []

    try:
        parsed = xmltodict.parse(xml_content)
        consolidated = parsed.get("CONSOLIDATED_LIST", {})

        if search_type == "person":
            individuals = _ensure_list(consolidated.get("INDIVIDUALS", {}).get("INDIVIDUAL"))
            for ind in individuals:
                result = _process_un_entry(ind, query_parts, is_person=True)
                if result:
                    matches.append(result)
        else:
            entities = _ensure_list(consolidated.get("ENTITIES", {}).get("ENTITY"))
            for ent in entities:
                result = _process_un_entry(ent, query_parts, is_person=False)
                if result:
                    matches.append(result)

    except Exception as e:
        print(f"UN XML parsing error: {e}")

    return matches[:20]


def generate_un_evidence_html(matches: list, query: str) -> str:
    """Generate HTML evidence document for UN sanctions matches."""
    timestamp = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

    if matches:
        status_badge = '<span class="badge badge-high">GĂSIT</span>'
        status_text = f"{len(matches)} potrivire(i) găsită(e)"
    else:
        status_badge = '<span class="badge badge-low">NEGĂSIT</span>'
        status_text = "Nicio potrivire"

    html = f"""<!DOCTYPE html>
<html lang="ro">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dovadă ONU - {query}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --color-primary: #28274e;
            --color-bg: #ffffff;
            --color-white: #ffffff;
            --color-black: #1a1a1a;
            --color-gray-100: #f9fafb;
            --color-gray-200: #e5e7eb;
            --color-gray-500: #6b7280;
            --color-gray-600: #4b5563;
            --color-success: #059669;
            --color-warning: #d97706;
            --color-danger: #dc2626;
            --color-un: #009edb;
            --radius-sm: 4px;
            --radius-md: 8px;
            --radius-lg: 12px;
        }}
        
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: var(--color-bg);
            color: var(--color-black);
            padding: 40px;
            -webkit-font-smoothing: antialiased;
        }}
        
        .container {{ max-width: 800px; margin: 0 auto; }}
        
        .header {{ margin-bottom: 24px; }}
        
        .header-title-row {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 8px;
        }}
        
        h1 {{ font-size: 24px; font-weight: 700; color: var(--color-primary); }}
        
        .subtitle {{ font-size: 14px; color: var(--color-gray-600); margin-top: 8px; }}
        
        .badge {{
            display: inline-flex; align-items: center; padding: 4px 10px;
            font-size: 11px; font-weight: 600; text-transform: uppercase;
            letter-spacing: 0.3px; border-radius: 4px;
        }}
        
        .badge-low {{ background: #d1fae5; color: var(--color-success); }}
        .badge-high {{ background: #fee2e2; color: var(--color-danger); }}
        
        .summary-card {{
            background: var(--color-white); border: 1px solid var(--color-gray-200);
            border-radius: var(--radius-lg); padding: 24px; margin-bottom: 24px;
        }}
        
        .summary-header {{
            display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;
        }}
        
        .summary-title {{ font-size: 16px; font-weight: 600; }}
        .summary-text {{ font-size: 14px; color: var(--color-gray-600); }}
        
        .result-card {{
            background: var(--color-white); border: 1px solid var(--color-gray-200);
            border-radius: var(--radius-lg); overflow: hidden; margin-bottom: 16px;
        }}
        
        .result-card-header {{
            padding: 16px 20px; background: var(--color-gray-100);
            border-bottom: 1px solid var(--color-gray-200);
            display: flex; align-items: center; justify-content: space-between;
        }}
        
        .result-card-title {{ display: flex; align-items: center; gap: 10px; font-size: 15px; font-weight: 600; }}
        .result-card-body {{ padding: 20px; }}
        
        .match-item {{
            padding: 14px; background: var(--color-gray-100);
            border-radius: var(--radius-sm); margin-bottom: 12px;
            border-left: 3px solid var(--color-warning);
        }}
        .match-item:last-child {{ margin-bottom: 0; }}
        
        .match-name {{ font-weight: 600; font-size: 15px; margin-bottom: 8px; color: var(--color-danger); }}
        
        .match-details {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 10px; }}
        
        .detail-item {{ font-size: 13px; }}
        .detail-label {{ font-weight: 600; color: var(--color-gray-500); text-transform: uppercase; font-size: 11px; display: block; margin-bottom: 2px; }}
        .detail-value {{ color: var(--color-black); }}
        
        .match-comments {{
            font-size: 13px; color: var(--color-gray-600); line-height: 1.5;
            margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--color-gray-200);
        }}
        
        .no-match {{
            padding: 24px; color: var(--color-success); background: #ecfdf5;
            border-radius: var(--radius-md); border: 1px solid #a7f3d0;
        }}
        .no-match h3 {{ font-size: 16px; margin-bottom: 4px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-title-row">
                <h1>Verificare listă consolidată ONU</h1>
            </div>
            <p class="subtitle">
                Interogare: <strong>{query}</strong> | Generat: {timestamp}
            </p>
        </div>

        <div class="summary-card">
            <div class="summary-header">
                <span class="summary-title">Rezultatul verificării</span>
                {status_badge}
            </div>
            <p class="summary-text">{status_text} în lista consolidată a Consiliului de Securitate ONU.</p>
        </div>
"""

    if matches:
        html += """
        <div class="result-card">
            <div class="result-card-header">
                <div class="result-card-title">Potriviri găsite</div>
            </div>
            <div class="result-card-body">
"""
        for match in matches:
            comments = match.get('comments', '')
            comments_html = f'<div class="match-comments">{comments}</div>' if comments else ''

            html += f"""
                <div class="match-item">
                    <div class="match-name">{match.get('name', 'Necunoscut')}</div>
                    <div class="match-details">
                        <div class="detail-item">
                            <span class="detail-label">Număr de referință</span>
                            <span class="detail-value">{match.get('reference_number', 'N/A')}</span>
                        </div>
                        <div class="detail-item">
                            <span class="detail-label">Tip listă</span>
                            <span class="detail-value">{match.get('un_list_type', 'N/A')}</span>
                        </div>
                        <div class="detail-item">
                            <span class="detail-label">Data listării</span>
                            <span class="detail-value">{match.get('listed_on', 'N/A')}</span>
                        </div>
                        <div class="detail-item">
                            <span class="detail-label">ID Date</span>
                            <span class="detail-value">{match.get('dataid', 'N/A')}</span>
                        </div>
                    </div>
                    {comments_html}
                </div>
"""
        html += """
            </div>
        </div>
"""
    else:
        html += """
        <div class="no-match">
            <h3>Nicio potrivire găsită</h3>
            <p>Numele sau entitatea căutată nu a fost găsită în lista consolidată a Consiliului de Securitate ONU.</p>
        </div>
"""

    html += """
    </div>
</body>
</html>
"""
    return html


# ============== AI Analysis ==============

def analyze_with_ai(query: str, search_type: str, eu_data: dict, un_matches: list) -> tuple[str, str]:
    """Use OpenAI to analyze risk and provide summary."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or api_key.startswith("sk-your"):
        eu_found = eu_data.get("found", False)
        un_found = len(un_matches) > 0

        if eu_found or un_found:
            match_info = []
            if eu_found:
                match_info.append(f"{len(eu_data.get('regimes', []))} EU regime(s)")
            if un_found:
                match_info.append(f"{len(un_matches)} potrivire(i) ONU")
            return "MEDIU", f"S-au gasit {', '.join(match_info)}. Se recomanda verificare manuala."
        return "SCAZUT", "Nu s-au gasit potriviri in bazele de date UE sau ONU."

    try:
        client = OpenAI(api_key=api_key)

        context = f"""
Analizeaza urmatoarele rezultate ale verificarii de sanctiuni:

Interogare: {query}
Tip: {search_type}

Rezultate Harta Sanctiunilor UE:
- Potriviri autocomplete: {eu_data.get('autocomplete', [])}
- Potriviri regim: {len(eu_data.get('regimes', []))} regim(uri)

Rezultate Consiliul de Securitate ONU:
{json.dumps(un_matches[:5], indent=2) if un_matches else "Nu s-au gasit potriviri"}

Ofera:
1. Un scor de risc (SCAZUT, MEDIU, RIDICAT, CRITIC)
2. Un sumar scurt (2-3 propozitii) in limba romana care explica rezultatele si actiunile recomandate.

Formateaza raspunsul astfel:
RISC: [scor]
SUMAR: [sumarul tau in romana]
"""

        messages = [{"role": "system",
                     "content": "Esti un analist de conformitate specializat in verificarea sanctiunilor. Raspunde intotdeauna in limba romana."},
                    {"role": "user", "content": context}]

        response = client.chat.completions.create(model="gpt-4o-mini", messages=messages, max_tokens=300,
                                                  temperature=0.3)

        result = response.choices[0].message.content.strip()

        risk_score = "MEDIU"
        summary = result

        if "RISC:" in result:
            lines = result.split("\n")
            for line in lines:
                if line.startswith("RISC:"):
                    risk_score = line.replace("RISC:", "").strip()
                elif line.startswith("SUMAR:"):
                    summary = line.replace("SUMAR:", "").strip()

        return risk_score, summary

    except Exception as e:
        print(f"AI analysis error: {e}")
        eu_found = eu_data.get("found", False)
        if eu_found or un_matches:
            return "MEDIU", "S-au gasit potriviri in bazele de date de sanctiuni. Se recomanda verificare manuala."
        return "SCAZUT", "Nu s-au gasit potriviri in bazele de date UE sau ONU."


# ============== Main Search Endpoint ==============

@app.post("/search", response_model=SearchResult)
async def search_sanctions(request: SearchRequest):
    """Main sanctions screening endpoint."""
    query = request.name.strip()
    search_type = request.search_type.lower()

    if not query:
        raise HTTPException(status_code=400, detail="Name is required")

    if search_type not in ["person", "entity"]:
        raise HTTPException(status_code=400, detail="search_type must be 'person' or 'entity'")

    audit_folder = generate_audit_folder_path(query)
    evidence_urls = {}

    # 1. Search EU Sanctions (autocomplete + regime)
    eu_data = await search_eu_sanctions(query)
    eu_found = eu_data.get("found", False)

    eu_matches = []
    for name in eu_data.get("autocomplete", []):
        eu_matches.append({"type": "person_match", "name": name})
    for regime in eu_data.get("regimes", []):
        country_title = None
        try:
            country_data = regime.get("country")
            if isinstance(country_data, dict):
                inner = country_data.get("data")
                if isinstance(inner, dict):
                    country_title = inner.get("title")
                elif isinstance(inner, list) and len(inner) > 0 and isinstance(inner[0], dict):
                    country_title = inner[0].get("title")
            elif isinstance(country_data, list) and len(country_data) > 0:
                if isinstance(country_data[0], dict):
                    country_title = country_data[0].get("title") or country_data[0].get("data", {}).get("title")
        except Exception:
            pass

        measure_titles = []
        try:
            measures_data = regime.get("measures")
            if isinstance(measures_data, dict):
                measures_list = measures_data.get("data", [])
            elif isinstance(measures_data, list):
                measures_list = measures_data
            else:
                measures_list = []

            for m in measures_list:
                if isinstance(m, dict):
                    m_type = m.get("type")
                    if isinstance(m_type, dict):
                        m_data = m_type.get("data")
                        if isinstance(m_data, dict):
                            title = m_data.get("title")
                            if title:
                                measure_titles.append(title)
        except Exception:
            pass

        eu_matches.append({"type": "regime", "id": regime.get("id"), "acronym": regime.get("acronym"),
                           "specification": regime.get("specification"), "country": country_title,
                           "measures": measure_titles})

    # 2. Take EU screenshot as PDF
    try:
        pdf_bytes = await take_eu_sanctions_screenshot(query)
        eu_pdf_key = f"{audit_folder}/evidence_eu.pdf"
        upload_to_spaces(pdf_bytes, eu_pdf_key, "application/pdf")
        evidence_urls["eu_evidence"] = get_presigned_url(eu_pdf_key)
    except Exception as e:
        print(f"EU PDF screenshot error: {e}")
        evidence_urls["eu_evidence"] = None

    # 3. Search UN Sanctions
    un_xml = get_un_xml()
    un_matches = search_un_sanctions(un_xml, query, search_type) if un_xml else []
    un_found = len(un_matches) > 0

    # 4. Generate UN evidence HTML and convert to PDF
    un_html = generate_un_evidence_html(un_matches, query)

    un_html_key = f"{audit_folder}/evidence_un.html"
    upload_to_spaces(un_html, un_html_key, "text/html")

    try:
        un_html_url = get_presigned_url(un_html_key)
        un_pdf_bytes = await take_screenshot_as_pdf(un_html_url, wait_time=2000)
        un_pdf_key = f"{audit_folder}/evidence_un.pdf"
        upload_to_spaces(un_pdf_bytes, un_pdf_key, "application/pdf")
        evidence_urls["un_evidence"] = get_presigned_url(un_pdf_key)
    except Exception as e:
        print(f"UN PDF generation error: {e}")
        evidence_urls["un_evidence"] = get_presigned_url(un_html_key)

    # 5. AI Analysis
    risk_score, ai_summary = analyze_with_ai(query, search_type, eu_data, un_matches)

    # 6. Generate audit logs
    timestamp = datetime.now(timezone.utc).isoformat()

    raw_data = {"query": query, "search_type": search_type, "timestamp": timestamp, "eu_data": eu_data,
                "un_matches": un_matches, "risk_score": risk_score, "ai_summary": ai_summary}

    raw_data_key = f"{audit_folder}/raw_data.json"
    upload_to_spaces(json.dumps(raw_data, indent=2, default=str), raw_data_key, "application/json")
    evidence_urls["raw_data"] = get_presigned_url(raw_data_key)

    audit_log = f"""Sanctions Screening Audit Log
=============================
Timestamp: {timestamp}
Query: {query}
Type: {search_type}

EU Sanctions Map:
- Autocomplete Matches: {len(eu_data.get('autocomplete', []))}
- Regime Matches: {len(eu_data.get('regimes', []))}
- Status: {'MATCH' if eu_found else 'CLEAR'}

UN Security Council:
- Matches Found: {len(un_matches)}
- Status: {'MATCH' if un_found else 'CLEAR'}

Risk Assessment:
- Score: {risk_score}
- Summary: {ai_summary}

Evidence Files:
- EU Evidence: evidence_eu.pdf
- UN Evidence: evidence_un.pdf
- Raw Data: raw_data.json

=============================
End of Audit Log
"""

    audit_log_key = f"{audit_folder}/audit_log.txt"
    upload_to_spaces(audit_log, audit_log_key, "text/plain")
    evidence_urls["audit_log"] = get_presigned_url(audit_log_key)

    return SearchResult(query=query, search_type=search_type, eu_found=eu_found, eu_matches=eu_matches[:10],
                        un_found=un_found, un_matches=un_matches[:10], risk_score=risk_score, ai_summary=ai_summary,
                        evidence_urls=evidence_urls, audit_folder=audit_folder)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    un_cached = UN_XML_LOCAL_PATH.exists()
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat(), "un_xml_cached": un_cached,
            "un_xml_date": get_cached_un_xml_date().isoformat() if get_cached_un_xml_date() else None}


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {"name": "Sanctions Screening API", "version": "1.0.0", "docs": "/docs", "health": "/health"}
