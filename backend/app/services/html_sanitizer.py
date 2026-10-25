"""HTML sanitization and structured job metadata extraction."""

import json
import re
from typing import Any, Dict, Optional, Tuple
from bs4 import BeautifulSoup


def sanitize_html_content(raw_html: str) -> str:
    """
    Strips executable scripts, stylesheets, iframes, objects, embeds,
    and event attributes from HTML to ensure safe presentation.
    """
    if not raw_html:
        return ""

    soup = BeautifulSoup(raw_html, "html.parser")

    # Remove dangerous elements
    for element in soup(["script", "style", "iframe", "object", "embed", "applet", "meta", "link"]):
        element.decompose()

    # Strip dangerous attributes from remaining tags
    for tag in soup.find_all(True):
        tag.attrs = {
            key: val
            for key, val in tag.attrs.items()
            if not key.lower().startswith("on") and key.lower() not in ("href", "src") or (
                key.lower() in ("href", "src") and not str(val).lower().strip().startswith("javascript:")
            )
        }

    return soup.get_text(separator="\n", strip=True)


def extract_job_from_html(html_text: str, base_url: str) -> Dict[str, Any]:
    """
    Extracts structured job posting information from HTML using:
    1. Schema.org JobPosting JSON-LD
    2. OpenGraph / Twitter meta tags
    3. Semantic HTML title & body fallback
    """
    soup = BeautifulSoup(html_text, "html.parser")

    title: Optional[str] = None
    company: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    employment_type: str = "full_time"
    work_mode: str = "unspecified"
    canonical_url: str = base_url

    # 1. Look for canonical link tag
    canonical_tag = None
    for link in soup.find_all("link"):
        rel_val = link.get("rel")
        if rel_val:
            rel_str = " ".join(rel_val) if isinstance(rel_val, list) else str(rel_val)
            if "canonical" in rel_str.lower():
                canonical_tag = link
                break
    if canonical_tag and canonical_tag.get("href"):
        canonical_url = str(canonical_tag.get("href")).strip()

    # 2. Try JSON-LD schemas
    json_ld_scripts = soup.find_all("script", type="application/ld+json")
    for script in json_ld_scripts:
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
            # Can be a single dict or a list of dicts, or @graph
            candidates = []
            if isinstance(data, dict):
                if data.get("@type") == "JobPosting":
                    candidates.append(data)
                elif "@graph" in data and isinstance(data["@graph"], list):
                    candidates.extend([item for item in data["@graph"] if isinstance(item, dict) and item.get("@type") == "JobPosting"])
            elif isinstance(data, list):
                candidates.extend([item for item in data if isinstance(item, dict) and item.get("@type") == "JobPosting"])

            if candidates:
                job_data = candidates[0]
                title = job_data.get("title")
                hiring_org = job_data.get("hiringOrganization")
                if isinstance(hiring_org, dict):
                    company = hiring_org.get("name")
                elif isinstance(hiring_org, str):
                    company = hiring_org

                raw_desc = job_data.get("description", "")
                if raw_desc:
                    description = sanitize_html_content(raw_desc)

                job_loc = job_data.get("jobLocation")
                if isinstance(job_loc, dict):
                    address = job_loc.get("address")
                    if isinstance(address, dict):
                        parts = [address.get("addressLocality"), address.get("addressRegion"), address.get("addressCountry")]
                        location = ", ".join([p for p in parts if p])
                    elif isinstance(address, str):
                        location = address
                elif isinstance(job_loc, list) and job_loc:
                    first_loc = job_loc[0]
                    if isinstance(first_loc, dict) and "address" in first_loc:
                        addr = first_loc["address"]
                        if isinstance(addr, dict):
                            parts = [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")]
                            location = ", ".join([p for p in parts if p])

                emp_type = job_data.get("employmentType")
                if emp_type:
                    if isinstance(emp_type, list):
                        emp_type = emp_type[0]
                    emp_type_str = str(emp_type).lower()
                    if "part" in emp_type_str:
                        employment_type = "part_time"
                    elif "contract" in emp_type_str:
                        employment_type = "contract"
                    elif "intern" in emp_type_str:
                        employment_type = "internship"
                    else:
                        employment_type = "full_time"

                # Check work mode
                job_location_type = str(job_data.get("jobLocationType", "")).upper()
                if "TELECOMMUTE" in job_location_type or (location and "remote" in location.lower()):
                    work_mode = "remote"

                break
        except Exception:
            continue

    # 3. Fallback to OpenGraph / Meta tags
    if not title:
        og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "twitter:title"})
        if og_title and og_title.get("content"):
            title = str(og_title.get("content")).strip()

    if not company:
        og_site = soup.find("meta", property="og:site_name") or soup.find("meta", attrs={"name": "author"})
        if og_site and og_site.get("content"):
            company = str(og_site.get("content")).strip()

    if not description:
        og_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
        if og_desc and og_desc.get("content"):
            description = str(og_desc.get("content")).strip()

    # 4. Fallback to HTML Title & Main Content
    if not title:
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            title = title_tag.string.strip()

    if not company:
        # Infer company from title pattern e.g. "Software Engineer at Acme" or "Acme - Senior Dev"
        if title:
            if " at " in title:
                parts = title.split(" at ")
                company = parts[-1].strip()
                title = parts[0].strip()
            elif " - " in title:
                parts = title.split(" - ")
                if len(parts) >= 2:
                    company = parts[0].strip()
                    title = parts[1].strip()

    if not company:
        company = "Unknown Company"

    if not title:
        title = "Job Opportunity"

    if not description:
        # Extract main text
        main_elem = soup.find("main") or soup.find("article") or soup.find("body")
        if main_elem:
            description = sanitize_html_content(str(main_elem))[:4000]
        else:
            description = "Job description extracted from imported URL."

    # Infer work mode if unspecified
    body_text = soup.get_text().lower()
    combined_text = f"{title} {location or ''} {description} {body_text}".lower()
    if work_mode == "unspecified":
        if "remote" in combined_text or "work from home" in combined_text:
            work_mode = "remote"
        elif "hybrid" in combined_text:
            work_mode = "hybrid"
        elif location:
            work_mode = "onsite"

    return {
        "title": title[:255],
        "company": company[:255],
        "description": description,
        "location": location[:255] if location else None,
        "work_mode": work_mode,
        "employment_type": employment_type,
        "canonical_url": canonical_url[:512],
    }
