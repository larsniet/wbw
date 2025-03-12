import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import cloudscraper
from bs4 import BeautifulSoup
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def unescape_selector(selector: str) -> str:
    """Unescape a CSS selector to get the raw ID/class name."""
    # Remove the initial # or . if present
    if selector.startswith('#') or selector.startswith('.'):
        selector = selector[1:]
    
    # Unescape spaces and other escaped characters
    selector = re.sub(r'\\([^A-Fa-f0-9])', r'\1', selector)
    selector = re.sub(r'\\([A-Fa-f0-9]{2})', lambda m: chr(int(m.group(1), 16)), selector)
    return selector

class PageMonitor:
    def __init__(self):
        self.scraper = None
        self.should_stop = False

    def stop(self):
        """Signal that monitoring should stop."""
        self.should_stop = True
        self.close_driver()

    def init_driver(self):
        """Initialize cloudscraper session."""
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'mobile': False,
                'custom': {
                    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                    'accept-language': 'en-US,en;q=0.9',
                    'upgrade-insecure-requests': '1',
                    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
                }
            }
        )
        logger.info("Initialized cloudscraper session")

    def close_driver(self):
        """Clean up resources."""
        if self.scraper:
            self.scraper = None

    def check_buttons(self, url: str, selectors: List[str], timeout: int = 30) -> Tuple[bool, Dict[str, str], Optional[str]]:
        """Check for buttons using cloudscraper."""
        if self.should_stop:
            return False, {}, "Operation cancelled by user"

        if not self.scraper:
            try:
                self.init_driver()
            except Exception as e:
                return False, {}, f"Failed to initialize scraper: {str(e)}"

        try:
            logger.info(f"Loading {url}")
            response = self.scraper.get(
                url, 
                timeout=timeout,
                headers={
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                    'sec-ch-ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"Windows"',
                    'sec-fetch-dest': 'document',
                    'sec-fetch-mode': 'navigate',
                    'sec-fetch-site': 'none',
                    'sec-fetch-user': '?1'
                }
            )
            response.raise_for_status()
            
            if self.should_stop:
                return False, {}, "Operation cancelled by user"
            
            # Parse the HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Debug: Log all elements with IDs
            elements_with_ids = soup.find_all(id=True)
            logger.info(f"Found {len(elements_with_ids)} elements with IDs on the page")
            for elem in elements_with_ids:
                logger.info(f"Element with ID: {elem.get('id')} (tag: {elem.name})")
            
            # Find selectors
            button_texts = {}
            for sel in selectors:
                if self.should_stop:
                    return False, {}, "Operation cancelled by user"
                
                # Handle ID selectors
                if sel.startswith('#'):
                    raw_id = unescape_selector(sel)
                    # Try exact match first
                    element = soup.find(id=raw_id)
                    
                    # If not found, try case-insensitive match
                    if not element:
                        element = soup.find(lambda tag: tag.get('id', '').lower() == raw_id.lower())
                    
                    # If still not found, try partial match
                    if not element:
                        element = soup.find(lambda tag: tag.get('id', '').lower() in raw_id.lower() or raw_id.lower() in tag.get('id', '').lower())
                    
                    if not element:
                        logger.error(f"Could not find element with ID: {raw_id}")
                        logger.info("Page content preview:")
                        logger.info(soup.prettify()[:1000])  # Log first 1000 chars of HTML
                        return False, {}, f"Button with ID '{raw_id}' not found"
                
                # Handle class selectors
                elif sel.startswith('.'):
                    raw_class = unescape_selector(sel)
                    element = soup.find(class_=raw_class)
                
                # Handle other CSS selectors
                else:
                    element = soup.select_one(sel)
                
                if not element:
                    logger.error(f"Could not find element with selector: {sel}")
                    return False, {}, f"Button with selector '{sel}' not found"
                
                button_texts[sel] = element.get_text().strip()
                logger.info(f"Found element {sel}: {button_texts[sel]}")
            
            return True, button_texts, None

        except cloudscraper.exceptions.CloudflareChallengeError as e:
            logger.error(f"Cloudflare challenge error: {e}")
            return False, {}, "Failed to bypass Cloudflare protection"
        
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            logger.exception("Full traceback:")
            return False, {}, f"Error loading page: {str(e)}"

    def has_changes(self, old_texts: Dict[str, str], new_texts: Dict[str, str]) -> bool:
        """Compare old and new button texts to detect changes."""
        if not old_texts:
            return False
        return old_texts != new_texts

    def should_stop_monitoring(self, start_time: datetime, max_duration: timedelta = timedelta(hours=12)) -> bool:
        """Check if monitoring should stop based on duration."""
        return datetime.now() - start_time > max_duration

    def __del__(self):
        self.close_driver() 