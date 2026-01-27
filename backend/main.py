"""
FastAPI Backend for Sanctions Screening PoC.
Integrates EU Sanctions Map, UN Security Council, and AI analysis.
All evidence stored statelessly in DigitalOcean Spaces.
"""

import concurrent.futures
import json
import os
import urllib.parse
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Optional

import httpx
import xmltodict
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from playwright.sync_api import sync_playwright
from pydantic import BaseModel

from storage import (upload_to_spaces, get_presigned_url, generate_audit_folder_path)

# Load environment variables
load_dotenv()

# Initialize FastAPI
app = FastAPI(title="Sanctions Screening API",
              description="Production-ready sanctions screening with EU and UN data sources", version="1.0.0")

# CORS configuration
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"],
                   allow_headers=["*"])

# Constants
EU_SANCTIONS_AUTOCOMPLETE_URL = "https://www.sanctionsmap.eu/api/v1/autocomplete/search"
EU_SANCTIONS_REGIME_URL = "https://www.sanctionsmap.eu/api/v1/regime"
EU_SANCTIONS_BASE_URL = "https://www.sanctionsmap.eu"
UN_CONSOLIDATED_URL = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"

# Local cache paths
LOCAL_CACHE_DIR = Path(__file__).parent / "cache"
UN_XML_LOCAL_PATH = LOCAL_CACHE_DIR / "consolidated.xml"
UN_XML_DATE_FILE = LOCAL_CACHE_DIR / "consolidated_date.txt"

# Spaces cache key
UN_XML_SPACES_KEY = "cache/consolidated.xml"


class SearchRequest(BaseModel):
    name: str
    search_type: str = "person"  # "person" or "entity"


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

    # Check if already downloaded today
    if cached_date == today:
        local_content = load_un_xml_locally()
        if local_content:
            print(f"Using locally cached UN XML from {cached_date}")
            return local_content

    # Delete old cache if exists
    if UN_XML_LOCAL_PATH.exists():
        print(f"Deleting old UN XML cache from {cached_date}")
        UN_XML_LOCAL_PATH.unlink()
    if UN_XML_DATE_FILE.exists():
        UN_XML_DATE_FILE.unlink()

    # Download fresh
    print("Downloading fresh UN consolidated XML...")
    xml_content = await download_un_xml()

    # Save locally
    save_un_xml_locally(xml_content)

    # Also upload to DO Spaces for backup
    try:
        upload_to_spaces(xml_content, UN_XML_SPACES_KEY, "application/xml")
        print(f"UN XML synced to Spaces: {UN_XML_SPACES_KEY}")
    except Exception as e:
        print(f"Warning: Failed to sync UN XML to Spaces: {e}")

    return xml_content


# Global variable to hold cached XML
_un_xml_cache: Optional[bytes] = None


@app.on_event("startup")
async def startup_event():
    """Download UN XML on application startup."""
    global _un_xml_cache
    try:
        _un_xml_cache = await ensure_un_xml_cached()
        print("UN XML ready for sanctions screening")
    except Exception as e:
        print(f"Warning: Failed to download UN XML on startup: {e}")


def get_un_xml() -> Optional[bytes]:
    """Get the cached UN XML content."""
    global _un_xml_cache
    if _un_xml_cache:
        return _un_xml_cache
    # Try to load from local cache
    return load_un_xml_locally()


# ============== EU Sanctions Integration ==============

EU_HEADERS = {"Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9",
              "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
              "Referer": "https://www.sanctionsmap.eu/",
              "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"', "sec-ch-ua-mobile": "?0",
              "sec-ch-ua-platform": '"Windows"', }


async def search_eu_autocomplete(name: str) -> list:
    """
    Query EU Sanctions Map autocomplete API.
    Returns list of matching names.
    """
    async with httpx.AsyncClient(timeout=30.0, headers=EU_HEADERS) as client:
        try:
            response = await client.get(EU_SANCTIONS_AUTOCOMPLETE_URL,
                                        params={"lang": "en", "search": name, "search_type": 1, "limit": 15})
            response.raise_for_status()
            data = response.json()
            # API returns {"data": ["Name1", "Name2"], "meta": {...}}
            return data.get("data", [])
        except Exception as e:
            print(f"EU Autocomplete API error: {e}")
            return []


async def search_eu_regime(name: str) -> list:
    """
    Query EU Sanctions Map regime API for detailed results.
    Returns list of regime/sanction matches.
    """
    async with httpx.AsyncClient(timeout=30.0, headers=EU_HEADERS) as client:
        try:
            response = await client.get(EU_SANCTIONS_REGIME_URL,
                                        params={"lang": "en", "search": name, "search_type": 1})
            response.raise_for_status()
            data = response.json()
            # API returns {"data": [...regimes...], "meta": {...}}
            return data.get("data", [])
        except Exception as e:
            print(f"EU Regime API error: {e}")
            return []


async def search_eu_sanctions(name: str) -> dict:
    """
    Full EU sanctions search: autocomplete + regime details.
    """
    # First check autocomplete for name matches
    autocomplete_matches = await search_eu_autocomplete(name)

    # Check if the searched name actually appears in autocomplete results
    # This indicates the person/entity actually exists in the EU sanctions list
    name_lower = name.lower()
    name_found_in_autocomplete = any(
        name_lower in match.lower() or match.lower() in name_lower for match in autocomplete_matches)

    # Only fetch regime details if we have an autocomplete match
    regime_matches = []
    if name_found_in_autocomplete:
        regime_matches = await search_eu_regime(name)

    return {"autocomplete": autocomplete_matches, "regimes": regime_matches,
            # Only mark as found if the name actually appears in autocomplete
            "found": name_found_in_autocomplete}


def generate_eu_deep_link(query: str) -> str:
    """Generate a deep link URL to the EU Sanctions Map for a search."""
    search_obj = {"value": query, "searchType": {"id": 1, "title": "regimes, persons, entities"}}
    search_json = json.dumps(search_obj, separators=(',', ':'))
    encoded_search = urllib.parse.quote(search_json, safe='')
    return f"{EU_SANCTIONS_BASE_URL}/#/main?search={encoded_search}"


def _take_screenshot_as_pdf_sync(url: str, wait_time: int = 5000, wait_for_selector: str = None) -> bytes:
    """
    Take a screenshot of a page using Playwright (sync) and return as PDF.
    Uses sync API to avoid Windows/Python 3.13 asyncio subprocess issues.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        try:
            page.goto(url, wait_until="networkidle", timeout=60000)

            # Wait for specific content to load (for SPAs like EU Sanctions Map)
            if wait_for_selector:
                try:
                    page.wait_for_selector(wait_for_selector, timeout=15000)
                except Exception:
                    pass  # Continue even if selector not found

            # Additional wait for dynamic content to render
            page.wait_for_timeout(wait_time)

            # Generate PDF in landscape for better sanctions map viewing
            pdf_bytes = page.pdf(format="A4", landscape=True, print_background=True,
                                 margin={"top": "20px", "right": "20px", "bottom": "20px", "left": "20px"})
            return pdf_bytes
        finally:
            browser.close()


def _take_eu_sanctions_screenshot_sync(query: str) -> bytes:
    """
    Take a screenshot of EU Sanctions Map with the search query.
    Uses URL-based deep link which properly filters results.
    """
    import urllib.parse

    # Generate the deep link URL with proper search encoding
    search_obj = {"value": query, "searchType": {"id": 1, "title": "regimes, persons, entities"}}
    search_json = json.dumps(search_obj, separators=(',', ':'))
    encoded_search = urllib.parse.quote(search_json, safe='')
    url = f"https://www.sanctionsmap.eu/#/main?search={encoded_search}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        try:
            # Go to the search URL
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(3000)  # Wait for Angular to initialize

            # Wait for the page to stabilize and process the search parameter
            page.wait_for_timeout(5000)  # Additional wait for search to filter

            # Scroll down slightly to ensure table is in view
            page.evaluate("window.scrollBy(0, 200)")
            page.wait_for_timeout(1000)

            # Generate PDF in landscape
            pdf_bytes = page.pdf(format="A4", landscape=True, print_background=True,
                                 margin={"top": "20px", "right": "20px", "bottom": "20px", "left": "20px"})
            return pdf_bytes
        finally:
            browser.close()


async def take_screenshot_as_pdf(url: str, wait_time: int = 5000, wait_for_selector: str = None) -> bytes:
    """
    Async wrapper that runs sync Playwright in a thread pool.
    """
    import asyncio
    from functools import partial

    loop = None
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        pass

    # Create partial function with all arguments
    screenshot_func = partial(_take_screenshot_as_pdf_sync, url, wait_time, wait_for_selector)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        if loop:
            pdf_bytes = await loop.run_in_executor(executor, screenshot_func)
        else:
            # Fallback for non-async context
            pdf_bytes = screenshot_func()

    return pdf_bytes


async def take_eu_sanctions_screenshot(query: str) -> bytes:
    """
    Async wrapper for EU Sanctions Map screenshot with interaction.
    """
    import asyncio
    from functools import partial

    loop = None
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        pass

    screenshot_func = partial(_take_eu_sanctions_screenshot_sync, query)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        if loop:
            pdf_bytes = await loop.run_in_executor(executor, screenshot_func)
        else:
            pdf_bytes = screenshot_func()

    return pdf_bytes


# ============== UN Security Council Integration ==============

def search_un_sanctions(xml_content: bytes, name: str, search_type: str) -> list:
    """Parse UN XML and search for matching entries."""
    matches = []

    if not xml_content:
        return matches

    try:
        parsed = xmltodict.parse(xml_content)
        consolidated = parsed.get("CONSOLIDATED_LIST", {})

        name_lower = name.lower()

        # Search individuals
        if search_type == "person":
            individuals = consolidated.get("INDIVIDUALS", {}).get("INDIVIDUAL", [])
            if isinstance(individuals, dict):
                individuals = [individuals]

            for ind in individuals:
                first_name = (ind.get("FIRST_NAME") or "").lower()
                second_name = (ind.get("SECOND_NAME") or "").lower()
                third_name = (ind.get("THIRD_NAME") or "").lower()
                full_name = f"{first_name} {second_name} {third_name}".strip()

                if name_lower in full_name or any(name_lower in n for n in [first_name, second_name, third_name] if n):
                    matches.append({"dataid": ind.get("DATAID"), "name": full_name.title(),
                                    "un_list_type": ind.get("UN_LIST_TYPE"),
                                    "reference_number": ind.get("REFERENCE_NUMBER"), "listed_on": ind.get("LISTED_ON"),
                                    "comments": ind.get("COMMENTS1", "")[:500] if ind.get("COMMENTS1") else ""})

        # Search entities
        else:
            entities = consolidated.get("ENTITIES", {}).get("ENTITY", [])
            if isinstance(entities, dict):
                entities = [entities]

            for ent in entities:
                entity_name = (ent.get("FIRST_NAME") or "").lower()

                if name_lower in entity_name:
                    matches.append({"dataid": ent.get("DATAID"), "name": entity_name.title(),
                                    "un_list_type": ent.get("UN_LIST_TYPE"),
                                    "reference_number": ent.get("REFERENCE_NUMBER"), "listed_on": ent.get("LISTED_ON"),
                                    "comments": ent.get("COMMENTS1", "")[:500] if ent.get("COMMENTS1") else ""})

    except Exception as e:
        print(f"UN XML parsing error: {e}")

    return matches[:20]


def generate_un_evidence_html(matches: list, query: str) -> str:
    """Generate HTML evidence document for UN sanctions matches."""
    timestamp = datetime.now(timezone.utc).isoformat()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>UN Sanctions Evidence - {query}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        .header {{ background: linear-gradient(135deg, #1a237e, #3949ab); color: white; padding: 30px; border-radius: 10px; margin-bottom: 30px; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .header p {{ margin: 10px 0 0 0; opacity: 0.9; }}
        .match {{ background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .match h3 {{ color: #c62828; margin-top: 0; }}
        .match-details {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; }}
        .detail label {{ font-weight: 600; color: #666; display: block; font-size: 12px; text-transform: uppercase; }}
        .detail span {{ color: #333; }}
        .no-match {{ background: #e8f5e9; border-left: 4px solid #4caf50; padding: 20px; border-radius: 4px; }}
        .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🇺🇳 UN Security Council Sanctions Check</h1>
        <p>Query: <strong>{query}</strong> | Generated: {timestamp}</p>
    </div>
"""

    if matches:
        html += f"<p><strong>{len(matches)} match(es) found</strong></p>"
        for match in matches:
            html += f"""
    <div class="match">
        <h3>⚠️ {match.get('name', 'Unknown')}</h3>
        <div class="match-details">
            <div class="detail">
                <label>Reference Number</label>
                <span>{match.get('reference_number', 'N/A')}</span>
            </div>
            <div class="detail">
                <label>List Type</label>
                <span>{match.get('un_list_type', 'N/A')}</span>
            </div>
            <div class="detail">
                <label>Listed On</label>
                <span>{match.get('listed_on', 'N/A')}</span>
            </div>
            <div class="detail">
                <label>Data ID</label>
                <span>{match.get('dataid', 'N/A')}</span>
            </div>
        </div>
        <p style="margin-top: 15px; color: #666;">{match.get('comments', '')}</p>
    </div>
"""
    else:
        html += """
    <div class="no-match">
        <h3>✅ No Matches Found</h3>
        <p>The searched name/entity was not found in the UN Security Council consolidated sanctions list.</p>
    </div>
"""

    html += """
    <div class="footer">
        <p>Source: UN Security Council Consolidated List | This document is auto-generated evidence for audit purposes.</p>
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
        # Fallback if no valid API key
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

        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system",
                                                                                  "content": "Esti un analist de conformitate specializat in verificarea sanctiunilor. Raspunde intotdeauna in limba romana."},
                                                                                 {"role": "user", "content": context}],
                                                  max_tokens=300, temperature=0.3)

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
            return "MEDIU", f"S-au gasit potriviri in bazele de date de sanctiuni. Se recomanda verificare manuala."
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

    # Generate audit folder path: {entity_name}/{timestamp}/
    audit_folder = generate_audit_folder_path(query)
    evidence_urls = {}

    # 1. Search EU Sanctions (autocomplete + regime)
    eu_data = await search_eu_sanctions(query)
    eu_found = eu_data.get("found", False)

    # Combine EU results for response
    eu_matches = []
    for name in eu_data.get("autocomplete", []):
        eu_matches.append({"type": "person_match", "name": name})
    for regime in eu_data.get("regimes", []):
        # Safely extract country - can have various nested structures
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

        # Safely extract measures
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

    # 2. Take EU screenshot as PDF - always capture the search page for evidence
    try:
        # Use the interactive EU screenshot function that types and searches
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

    # Save HTML first
    un_html_key = f"{audit_folder}/evidence_un.html"
    upload_to_spaces(un_html, un_html_key, "text/html")

    # Create UN evidence PDF using browser
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
