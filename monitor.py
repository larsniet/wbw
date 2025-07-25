import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
import cloudscraper
from bs4 import BeautifulSoup
import re
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

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
    def __init__(self, use_javascript: bool = False):
        self.scraper = None
        self.driver = None
        self.use_javascript = use_javascript
        self.should_stop = False

    def stop(self):
        """Signal that monitoring should stop."""
        self.should_stop = True
        self.close_driver()

    def init_driver(self):
        """Initialize scraper or browser driver based on mode."""
        if self.use_javascript:
            self.init_selenium_driver()
        else:
            self.init_cloudscraper()

    def init_cloudscraper(self):
        """Initialize cloudscraper session."""
        self.scraper = cloudscraper.create_scraper(
            browser={
                'custom_browser': 'chrome',
                'platform': 'windows',
                'desktop': True,
                'headers': {
                    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                    'accept-language': 'en-US,en;q=0.9',
                    'upgrade-insecure-requests': '1',
                    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
                }
            }
        )
        logger.info("Initialized cloudscraper session")

    def init_selenium_driver(self):
        """Initialize undetected Chrome driver for JavaScript execution."""
        options = uc.ChromeOptions()
        
        # Detect if running in Docker/CI environment
        is_docker = os.path.exists('/.dockerenv') or os.getenv('DISPLAY') == ':99'
        
        # Basic Chrome options
        options.add_argument('--no-first-run')
        options.add_argument('--no-service-autorun')
        options.add_argument('--no-default-browser-check')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-features=VizDisplayCompositor')
        
        # Docker/Headless specific options
        if is_docker:
            logger.info("Detected Docker environment - configuring for headless operation")
            options.add_argument('--headless=new')  # Use new headless mode
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-software-rasterizer')
            options.add_argument('--disable-background-timer-throttling')
            options.add_argument('--disable-backgrounding-occluded-windows')
            options.add_argument('--disable-renderer-backgrounding')
            options.add_argument('--disable-features=TranslateUI')
            options.add_argument('--disable-ipc-flooding-protection')
            options.add_argument('--window-size=1920,1080')
        else:
            logger.info("Detected local environment - running with visible browser")
            # For local development, don't run headless by default for easier debugging
            # options.add_argument('--headless=new')  # Uncomment to force headless locally
        
        try:
            self.driver = uc.Chrome(options=options)
            logger.info(f"Initialized undetected Chrome driver ({'headless' if is_docker else 'visible'} mode)")
        except Exception as e:
            logger.error(f"Failed to initialize Chrome driver: {e}")
            raise

    def close_driver(self):
        """Clean up resources."""
        if self.scraper:
            self.scraper = None
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.warning(f"Error closing driver: {e}")
            finally:
                self.driver = None

    def check_elements(self, url: str, selectors: List[str], timeout: int = 30, allow_missing: bool = False, js_wait_time: int = 5) -> Tuple[Union[bool, str], Dict[str, str], Optional[str]]:
        """Check for elements using cloudscraper or Selenium with JavaScript support."""
        if self.should_stop:
            return False, {}, "Operation cancelled by user"

        if self.use_javascript:
            return self._check_elements_selenium(url, selectors, timeout, allow_missing, js_wait_time)
        else:
            return self._check_elements_cloudscraper(url, selectors, timeout, allow_missing)

    def _check_elements_selenium(self, url: str, selectors: List[str], timeout: int, allow_missing: bool, js_wait_time: int) -> Tuple[Union[bool, str], Dict[str, str], Optional[str]]:
        """Check elements using Selenium WebDriver with JavaScript execution."""
        if not self.driver:
            try:
                self.init_driver()
            except Exception as e:
                return False, {}, f"Failed to initialize driver: {str(e)}"

        try:
            logger.info(f"Loading {url} with JavaScript support")
            self.driver.get(url)
            
            # Wait for page to load completely
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            
            # Additional wait for JavaScript to execute and inject content
            logger.info(f"Waiting {js_wait_time}s for JavaScript content to load...")
            time.sleep(js_wait_time)
            
            if self.should_stop:
                return False, {}, "Operation cancelled by user"
            
            # Get page source and parse with BeautifulSoup for debugging
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Debug logging (same as cloudscraper version)
            self._log_debug_info(soup)
            
            # Find elements using Selenium
            element_texts = {}
            missing_elements = []
            
            for sel in selectors:
                if self.should_stop:
                    return False, {}, "Operation cancelled by user"
                
                try:
                    # Wait for element to be present
                    element = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                    )
                    element_text = element.text.strip()
                    element_texts[sel] = element_text
                    logger.info(f"Found element {sel}: {element_text}")
                    
                except TimeoutException:
                    logger.error(f"Could not find element with selector: {sel}")
                    if not allow_missing:
                        return False, {}, f"Element with selector '{sel}' not found"
                    else:
                        missing_elements.append(sel)
                        continue
            
            # Handle missing elements
            if missing_elements and allow_missing:
                return "missing", element_texts, f"Missing elements: {', '.join(missing_elements)}"
            
            return True, element_texts, None

        except WebDriverException as e:
            logger.error(f"WebDriver error: {e}")
            return False, {}, f"WebDriver error: {str(e)}"
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            logger.exception("Full traceback:")
            return False, {}, f"Error loading page: {str(e)}"

    def _check_elements_cloudscraper(self, url: str, selectors: List[str], timeout: int, allow_missing: bool) -> Tuple[Union[bool, str], Dict[str, str], Optional[str]]:
        """Check for elements using cloudscraper (original implementation)."""
        if not self.scraper:
            try:
                self.init_driver()
            except Exception as e:
                return False, {}, f"Failed to initialize scraper: {str(e)}"

        try:
            # First check our IP address
            logger.info("Checking server IP address...")
            ip_response = self.scraper.get('https://api.ipify.org?format=json', timeout=5)
            ip_data = ip_response.json()
            logger.info(f"Server IP address: {ip_data['ip']}")

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
            # Add detailed logging of the response
            logger.info(f"Response status code: {response.status_code}")
            logger.info(f"Response headers: {dict(response.headers)}")
            logger.info(f"Response content preview: {response.text[:500]}")  # First 500 chars of response
            
            response.raise_for_status()
            
            if self.should_stop:
                return False, {}, "Operation cancelled by user"
            
            # Parse the HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Debug logging
            self._log_debug_info(soup)
            
            # Find selectors using BeautifulSoup
            element_texts = {}
            missing_elements = []
            
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
                    
                    if not element:
                        logger.error(f"Could not find element with ID: {raw_id}")
                        if not allow_missing:
                            logger.info("Page content preview:")
                            logger.info(soup.prettify()[:1000])  # Log first 1000 chars of HTML
                            return False, {}, f"Element with ID '{raw_id}' not found"
                        else:
                            missing_elements.append(sel)
                            continue
                
                # Handle class selectors and other CSS selectors
                else:
                    element = soup.select_one(sel)
                
                if not element:
                    logger.error(f"Could not find element with selector: {sel}")
                    if not allow_missing:
                        return False, {}, f"Element with selector '{sel}' not found"
                    else:
                        missing_elements.append(sel)
                        continue
                
                element_texts[sel] = element.get_text().strip()
                logger.info(f"Found element {sel}: {element_texts[sel]}")
            
            # If we have missing elements and allow_missing is True, return special status
            if missing_elements and allow_missing:
                return "missing", element_texts, f"Missing elements: {', '.join(missing_elements)}"
            
            return True, element_texts, None

        except cloudscraper.exceptions.CloudflareChallengeError as e:
            logger.error(f"Cloudflare challenge error: {e}")
            return False, {}, "Failed to bypass Cloudflare protection"
        
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            logger.exception("Full traceback:")
            return False, {}, f"Error loading page: {str(e)}"

    def _log_debug_info(self, soup: BeautifulSoup):
        """Log debug information about the page content."""
        # Debug: Log all elements with IDs
        elements_with_ids = soup.find_all(id=True)
        logger.info(f"Found {len(elements_with_ids)} elements with IDs on the page")
        for elem in elements_with_ids:
            logger.info(f"Element with ID: {elem.get('id')} (tag: {elem.name})")
        
        # Debug: Look for elements with classes that contain common patterns
        common_classes = ['error', 'alert', 'warning', 'message', 'notification', 'status', 'info']
        for class_pattern in common_classes:
            matching_elements = soup.find_all(class_=re.compile(class_pattern, re.IGNORECASE))
            logger.info(f"Found {len(matching_elements)} elements with class containing '{class_pattern}'")
            for elem in matching_elements:
                logger.info(f"Element classes: {elem.get('class', [])} (tag: {elem.name})")

    def has_changes(self, old_texts: Dict[str, str], new_texts: Dict[str, str]) -> bool:
        """Compare old and new element texts to detect changes."""
        if not old_texts:
            return False
        return old_texts != new_texts

    def should_stop_monitoring(self, start_time: datetime, max_duration: timedelta = timedelta(hours=12)) -> bool:
        """Check if monitoring should stop based on duration."""
        return datetime.now() - start_time > max_duration

    def __del__(self):
        self.close_driver() 