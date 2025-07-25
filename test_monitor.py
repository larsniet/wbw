#!/usr/bin/env python3
"""
Generic test script for JavaScript-aware page monitoring.
Tests element detection and monitoring on any website with any CSS selector.
Supports both static HTML parsing and JavaScript-enabled dynamic content detection.
"""

import sys
import logging
from monitor import PageMonitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_element_detection(url: str, selector: str, timeout: int = 30, use_javascript: bool = False, js_wait_time: int = 5):
    """
    Test element detection on any URL with any CSS selector.
    
    Args:
        url: The URL to test
        selector: The CSS selector to look for
        timeout: Timeout in seconds for page load
        use_javascript: Whether to use JavaScript execution
        js_wait_time: Time to wait for JavaScript content to load
    """
    mode = "JavaScript-enabled" if use_javascript else "Cloudscraper"
    print(f"\n{'='*60}")
    print(f"TESTING ELEMENT DETECTION ({mode})")
    print(f"{'='*60}")
    print(f"URL: {url}")
    print(f"Selector: {selector}")
    print(f"Timeout: {timeout}s")
    if use_javascript:
        print(f"JS wait time: {js_wait_time}s")
    print(f"{'='*60}\n")
    
    monitor = PageMonitor(use_javascript=use_javascript)
    
    try:
        # Test element detection
        success, element_texts, error = monitor.check_elements(
            url=url,
            selectors=[selector],
            timeout=timeout,
            allow_missing=False,
            js_wait_time=js_wait_time
        )
        
        print(f"\n{'='*60}")
        print(f"RESULTS")
        print(f"{'='*60}")
        
        if success is True:
            print("✅ SUCCESS: Element found!")
            print(f"Element text: '{element_texts.get(selector, 'No text')}'")
        elif success == "missing":
            print("⚠️  PARTIAL: Some elements missing")
            print(f"Found elements: {element_texts}")
            print(f"Error: {error}")
        else:
            print("❌ FAILED: Element not found")
            print(f"Error: {error}")
            
        print(f"{'='*60}\n")
        
        return success, element_texts, error
        
    except Exception as e:
        print(f"❌ EXCEPTION: {str(e)}")
        logger.exception("Full traceback:")
        return False, {}, str(e)
        
    finally:
        # Clean up
        monitor.close_driver()
        print("🧹 Cleaned up resources")

def test_monitoring_cycle(url: str, selector: str, cycles: int = 2, interval: int = 10, use_javascript: bool = False, js_wait_time: int = 5):
    """
    Test multiple monitoring cycles to detect changes.
    
    Args:
        url: The URL to monitor
        selector: The CSS selector to monitor
        cycles: Number of monitoring cycles to run
        interval: Seconds between checks
        use_javascript: Whether to use JavaScript execution
        js_wait_time: Time to wait for JavaScript content to load
    """
    mode = "JavaScript-enabled" if use_javascript else "Cloudscraper"
    print(f"\n{'='*60}")
    print(f"TESTING MONITORING CYCLES ({mode})")
    print(f"{'='*60}")
    print(f"URL: {url}")
    print(f"Selector: {selector}")
    print(f"Cycles: {cycles}")
    print(f"Interval: {interval}s")
    if use_javascript:
        print(f"JS wait time: {js_wait_time}s")
    print(f"{'='*60}\n")
    
    monitor = PageMonitor(use_javascript=use_javascript)
    previous_texts = {}
    
    try:
        for cycle in range(cycles):
            print(f"\n--- Cycle {cycle + 1}/{cycles} ---")
            
            success, element_texts, error = monitor.check_elements(
                url=url,
                selectors=[selector],
                timeout=30,
                allow_missing=True,
                js_wait_time=js_wait_time
            )
            
            if success is True:
                current_text = element_texts.get(selector, '')
                print(f"✅ Element found: '{current_text}'")
                
                # Check for changes
                if previous_texts and selector in previous_texts:
                    if monitor.has_changes({selector: previous_texts[selector]}, {selector: current_text}):
                        print("🔄 CHANGE DETECTED!")
                        print(f"Previous: '{previous_texts[selector]}'")
                        print(f"Current:  '{current_text}'")
                    else:
                        print("📝 No change detected")
                else:
                    print("📝 First check - storing baseline")
                
                previous_texts[selector] = current_text
                
            elif success == "missing":
                print(f"⚠️  Element missing: {error}")
            else:
                print(f"❌ Error: {error}")
            
            # Wait between cycles (except last one)
            if cycle < cycles - 1:
                print(f"⏳ Waiting {interval}s until next check...")
                import time
                time.sleep(interval)
                
    except Exception as e:
        print(f"❌ EXCEPTION: {str(e)}")
        logger.exception("Full traceback:")
        
    finally:
        monitor.close_driver()
        print("\n🧹 Cleaned up resources")

def main():
    """Main test function with configurable parameters."""
    
    # Parse command line arguments
    if len(sys.argv) < 3:
        print("🚀 JavaScript-aware Page Monitor Test")
        print(f"Usage: python test_monitor.py <URL> <CSS_SELECTOR> [--js|-j]")
        print(f"")
        print(f"Arguments:")
        print(f"  URL         : The website URL to monitor")
        print(f"  CSS_SELECTOR: The CSS selector to look for (e.g., '.error-message' or '#status')")
        print(f"  --js|-j     : Enable JavaScript execution (for dynamic content)")
        print(f"")
        print(f"Examples:")
        print(f"  python test_monitor.py 'https://example.com' '.error-message'")
        print(f"  python test_monitor.py 'https://example.com' '#status' --js")
        return
    
    url = sys.argv[1]
    selector = sys.argv[2]
    
    # Check for JavaScript flag
    use_javascript = "--js" in sys.argv or "-j" in sys.argv
    
    print("🚀 Starting JavaScript-aware Page Monitor Test")
    print(f"Usage: python test_monitor.py <URL> <CSS_SELECTOR> [--js|-j]")
    print(f"Current test parameters:")
    print(f"  URL: {url}")
    print(f"  Selector: {selector}")
    print(f"  JavaScript mode: {'Enabled' if use_javascript else 'Disabled (use --js to enable)'}")
    
    try:
        # Test 1: Single element detection
        print("\n🔍 TEST 1: Element Detection")
        success, texts, error = test_element_detection(url, selector, use_javascript=use_javascript)
        
        # Test 2: Multiple monitoring cycles (only if first test succeeded)
        if success:
            print("\n🔄 TEST 2: Monitoring Cycles")
            test_monitoring_cycle(url, selector, cycles=2, interval=5, use_javascript=use_javascript)
        else:
            print("\n⏭️  Skipping monitoring cycle test (element not found)")
            
            # If cloudscraper failed and JS mode is not enabled, suggest trying JS mode
            if not use_javascript:
                print("\n💡 TIP: Try adding --js flag to enable JavaScript execution:")
                print(f"   python test_monitor.py \"{url}\" \"{selector}\" --js")
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        logger.exception("Full traceback:")
    
    print("\n✅ Test completed!")

if __name__ == "__main__":
    main() 