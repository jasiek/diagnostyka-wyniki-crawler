"""
Wyniki.diag.pl crawler - retrieves blood test results as XML
"""

import os
import re
import asyncio
import argparse
from pathlib import Path
from datetime import datetime
from playwright.async_api import (
    async_playwright,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)
from dotenv import load_dotenv


class WynikiCrawler:
    """Crawler for wyniki.diag.pl blood test results"""

    def __init__(
        self,
        username: str,
        password: str,
        download_dir: str = "downloads",
        profile_dir: str = ".playwright/wyniki-profile",
        headless: bool = False,
        cdp_url: str | None = None,
        ignore_incapsula: bool = False,
        interactive_browser: bool = False,
        remote_debugging_port: int = 9222,
    ):
        self.username = username
        self.password = password
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.profile_dir = Path(profile_dir)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.cdp_url = cdp_url
        self.ignore_incapsula = ignore_incapsula
        self.interactive_browser = interactive_browser
        self.remote_debugging_port = remote_debugging_port
        self.base_url = "https://wyniki.diag.pl"

    async def is_blocked(self, page: Page) -> bool:
        """Detect the Imperva/Incapsula block page."""
        content = await page.content()
        if self.ignore_incapsula:
            return False
        return "Incapsula" in content or "_Incapsula_Resource" in content

    async def is_logged_in(self, page: Page) -> bool:
        """Check whether the saved browser profile is still authenticated."""
        print("Checking saved browser session...")
        await page.goto(f"{self.base_url}/zlecenia", wait_until="domcontentloaded")

        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeoutError:
            pass

        await page.wait_for_timeout(1000)

        if await self.is_blocked(page):
            raise RuntimeError(
                "wyniki.diag.pl returned an Incapsula block page. "
                "Open the site in a normal Chrome session and use WYNIKI_CDP_URL, "
                "or retry later after the block clears."
            )

        login_inputs = await page.query_selector(
            "input[name='accountId'], input[name='password']"
        )
        if login_inputs:
            print("Saved browser session is not authenticated.")
            return False

        if "/zlecenia" in page.url:
            print("Using saved browser session.")
            return True

        print("Saved browser session is not authenticated.")
        return False

    async def login(self, page: Page) -> bool:
        """Log into wyniki.diag.pl"""
        print("Navigating to login page...")
        await page.goto(self.base_url, wait_until="networkidle")

        # Wait for the page to load (it's a SPA)
        await page.wait_for_timeout(2000)

        if await self.is_blocked(page):
            raise RuntimeError(
                "wyniki.diag.pl returned an Incapsula block page before login."
            )

        print(f"Logging in as {self.username}...")
        # Fill in the login form for "Konto Stałego Klienta"
        account_input = page.locator("input[name='accountId']").first
        password_input = page.locator("input[name='password']").first
        await account_input.fill(self.username)
        await password_input.fill(self.password)

        await self.submit_login_form(page, password_input)

        # Check if we're redirected to 2FA page
        try:
            await page.wait_for_url(
                "**/uwierzytelnianie-dwuskladnikowe**", timeout=5000
            )
            print("\n" + "=" * 60)
            print("⚠️  TWO-FACTOR AUTHENTICATION REQUIRED")
            print("=" * 60)
            print("Please enter the SMS code in the browser window.")
            print("The script will continue automatically after you submit the code.")
            print("=" * 60 + "\n")

            # Wait for user to complete 2FA and navigate to orders list
            await page.wait_for_url(
                "**/zlecenia**", timeout=120000
            )  # 2 minute timeout for manual entry
            print("✓ Two-factor authentication completed!")
        except PlaywrightTimeoutError:
            # If no 2FA, wait directly for orders list
            await page.wait_for_url("**/zlecenia**", timeout=10000)

        print("Login successful!")
        return True

    async def submit_login_form(self, page: Page, password_input) -> None:
        """Submit the account login form across minor frontend selector changes."""
        submit_selectors = [
            "button[data-cy='submit-account-btn']",
            "button[type='submit']:has-text('Zaloguj')",
            "button:has-text('Zaloguj się')",
            "button:has-text('Zaloguj')",
        ]

        for selector in submit_selectors:
            locator = page.locator(selector).first
            try:
                if await locator.is_visible(timeout=3000):
                    await locator.click()
                    return
            except PlaywrightTimeoutError:
                continue

        print("Login submit button was not found; submitting password field with Enter.")
        await password_input.press("Enter")

    async def ensure_logged_in(self, page: Page) -> None:
        """Use the saved browser session when possible, otherwise log in."""
        if await self.is_logged_in(page):
            return

        await self.login(page)

    async def get_all_orders(self, page: Page) -> list:
        """Get all order links from the orders list page"""
        print("Fetching all orders...")

        if await self.is_blocked(page):
            raise RuntimeError(
                "wyniki.diag.pl returned an Incapsula block page on the orders page."
            )

        orders = []
        current_page = 1

        while True:
            # Wait for orders to load
            await page.wait_for_selector("a[data-cy='view-result-btn']", timeout=5000)

            # Get all order links on current page
            order_elements = await page.query_selector_all(
                "a[data-cy='view-result-btn']"
            )

            for element in order_elements:
                href = await element.get_attribute("href")
                if href:
                    orders.append(href)

            print(f"Found {len(order_elements)} orders on page {current_page}")

            # Check if there's a next page button
            next_button = await page.query_selector(
                "button[data-cy='pagination-next']:not([disabled])"
            )

            if next_button:
                print(f"Moving to page {current_page + 1}...")
                await next_button.click()
                await page.wait_for_timeout(1000)
                current_page += 1
            else:
                print("No more pages.")
                break

        print(f"Total orders found: {len(orders)}")
        return orders

    async def download_order_files(self, page: Page, order_url: str):
        """Download all XML and PDF files for a specific order"""
        # Navigate to order details page
        full_url = (
            f"{self.base_url}{order_url}"
            if not order_url.startswith("http")
            else order_url
        )
        await page.goto(full_url, wait_until="domcontentloaded")

        # Wait for the order details shell, then let the options/download
        # controls below determine readiness. The page contains hidden
        # "Wyniki badań" notification text that is not a reliable wait target.
        await page.locator("body").wait_for(state="visible", timeout=10000)
        await page.wait_for_timeout(1000)
        await self.open_download_options(page)

        order_number = await self.get_order_number_from_page(page, order_url)
        print(f"Processing order: {order_number}")

        # Find specific download buttons using data-cy attributes and aria-label
        xml_buttons = await page.query_selector_all(
            "button[data-cy='download-file-btn-Xml']"
        )
        pdf_buttons = await page.query_selector_all(
            "button[data-cy='download-file-btn-Pdf']"
        )
        csv_buttons = await page.query_selector_all(
            "[aria-label='Pobierz listę badań'], button:has-text('Pobierz listę badań')"
        )

        downloaded_count = 0

        # Download all XML files
        for i, xml_button in enumerate(xml_buttons):
            try:
                async with page.expect_download(timeout=30000) as download_info:
                    await xml_button.click()
                    await page.wait_for_timeout(500)

                download = await download_info.value
                suffix = f"_xml{i+1}" if len(xml_buttons) > 1 else ""
                filename = f"{order_number}{suffix}.xml"
                save_path = self.download_dir / filename
                await download.save_as(save_path)
                print(f"  ✓ Saved XML: {filename}")
                downloaded_count += 1
            except Exception as e:
                print(f"  ✗ Failed to download XML {i+1}: {e}")

        # Download all PDF files
        for i, pdf_button in enumerate(pdf_buttons):
            try:
                async with page.expect_download(timeout=30000) as download_info:
                    await pdf_button.click()
                    await page.wait_for_timeout(500)

                download = await download_info.value
                suffix = f"_pdf{i+1}" if len(pdf_buttons) > 1 else ""
                filename = f"{order_number}{suffix}.pdf"
                save_path = self.download_dir / filename
                await download.save_as(save_path)
                print(f"  ✓ Saved PDF: {filename}")
                downloaded_count += 1
            except Exception as e:
                print(f"  ✗ Failed to download PDF {i+1}: {e}")

        # Download all CSV files
        for i, csv_button in enumerate(csv_buttons):
            try:
                async with page.expect_download(timeout=30000) as download_info:
                    await csv_button.click()
                    await page.wait_for_timeout(500)

                download = await download_info.value
                suffix = f"_csv{i+1}" if len(csv_buttons) > 1 else ""
                filename = f"{order_number}{suffix}.csv"
                save_path = self.download_dir / filename
                await download.save_as(save_path)
                print(f"  ✓ Saved CSV: {filename}")
                downloaded_count += 1
            except Exception as e:
                print(f"  ✗ Failed to download CSV {i+1}: {e}")

        if downloaded_count == 0:
            print(f"  ⚠ No files downloaded for order {order_number}")

        # Close the dialog if there's a close button
        close_button = await page.query_selector(
            "button[aria-label='close'], button:has-text('Zamknij')"
        )
        if close_button:
            await close_button.click()
            await page.wait_for_timeout(500)

    async def open_download_options(self, page: Page) -> None:
        """Open the current download/options UI when it is collapsed."""
        download_buttons = await page.locator(
            "button[data-cy^='download-file-btn-'], [aria-label='Pobierz listę badań']"
        ).count()
        if download_buttons:
            return

        option_selectors = [
            "button[data-cy='get-tests-btn']",
            "button:has-text('Opcje')",
            "[role='button']:has-text('Opcje')",
        ]
        for selector in option_selectors:
            locator = page.locator(selector).first
            try:
                if await locator.is_visible(timeout=3000):
                    await locator.click()
                    await page.wait_for_timeout(1000)
                    return
            except PlaywrightTimeoutError:
                continue

        raise RuntimeError("Could not find the order download/options control")

    async def get_order_number_from_page(self, page: Page, order_url: str) -> str:
        """Extract order number from the order details page"""
        # Try multiple methods to extract order number

        # Method 1: Look for barcode with 'L' suffix
        order_number_element = await page.query_selector(
            "p.MuiTypography-body2:has-text('L')"
        )
        if order_number_element:
            order_number = await order_number_element.inner_text()
            return order_number.strip()

        # Method 2: Look for any barcode-like pattern
        all_paragraphs = await page.query_selector_all("p.MuiTypography-body2")
        for p in all_paragraphs:
            text = await p.inner_text()
            # Match patterns like 402337694L, 383634902L
            if text and len(text) > 5 and text[-1] == "L" and text[:-1].isdigit():
                return text.strip()

        # Method 3: Search all visible page text for a barcode-like value
        page_text = await page.locator("body").inner_text()
        match = re.search(r"\b\d{6,}L\b", page_text)
        if match:
            return match.group(0)

        # Method 4: Extract from URL path as last resort
        # URL format: /zlecenie/some-encrypted-id
        # Use the encrypted ID with timestamp for uniqueness
        url_parts = order_url.split("/")
        if len(url_parts) > 2:
            encrypted_id = url_parts[-1][:10]  # Take first 10 chars
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return f"order_{encrypted_id}_{timestamp}"

        # Last resort: timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"unknown_{timestamp}"

    async def crawl(self):
        """Main crawl function"""
        async with async_playwright() as p:
            if self.interactive_browser:
                await self.crawl_with_interactive_browser(p)
                return

            if self.cdp_url:
                browser = await p.chromium.connect_over_cdp(self.cdp_url)
                context = browser.contexts[0]
                page = next(
                    (
                        candidate
                        for candidate in context.pages
                        if candidate.url.startswith(self.base_url)
                    ),
                    context.pages[0] if context.pages else await context.new_page(),
                )

                try:
                    await self.run_crawl(page, trust_current_page=True)
                finally:
                    await browser.close()
                return

            # Persistent context keeps cookies, local storage, IndexedDB, and
            # other browser profile data so 2FA/session state can survive runs.
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=self.headless,
                accept_downloads=True,
            )
            page = context.pages[0] if context.pages else await context.new_page()

            try:
                await self.run_crawl(page)

            finally:
                await context.close()

    async def crawl_with_interactive_browser(self, playwright) -> None:
        """Launch one visible browser, wait for manual prep, then crawl it."""
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=False,
            accept_downloads=True,
            args=[f"--remote-debugging-port={self.remote_debugging_port}"],
        )
        page = context.pages[0] if context.pages else await context.new_page()

        try:
            await page.goto(self.base_url, wait_until="domcontentloaded")
            print("\nInteractive browser is open.")
            print("Use it to log in and open the laboratory orders page.")
            print("Leave the browser window open, then press Enter here to crawl.")
            try:
                await asyncio.to_thread(input)
            except EOFError:
                print("No interactive stdin is available; exiting without crawling.")
                return

            self.ignore_incapsula = True
            await self.run_crawl(page, trust_current_page=True)
        finally:
            await context.close()

    async def run_crawl(self, page: Page, trust_current_page: bool = False) -> None:
        """Run the crawl using an already-created page."""
        if trust_current_page:
            print(f"Using current browser page: {page.url}")
            if "/zlecenia/laboratoryjne?" not in page.url:
                await page.goto(
                    f"{self.base_url}/zlecenia/laboratoryjne?page=1",
                    wait_until="domcontentloaded",
                )
                await page.wait_for_timeout(1000)
        else:
            # Login only when the saved session has expired.
            await self.ensure_logged_in(page)

        # Get all orders
        order_urls = await self.get_all_orders(page)

        # Process each order
        for i, order_url in enumerate(order_urls, 1):
            print(f"\n[{i}/{len(order_urls)}] Processing order...")

            # Download all files (XML, PDF, and CSV)
            try:
                await self.download_order_files(page, order_url)
            except Exception as e:
                print(f"Error downloading files for order {order_url}: {e}")
                continue

            # Small delay between requests
            await page.wait_for_timeout(1000)

        print(
            f"\n✓ Crawl completed! Downloaded {len(order_urls)} orders to {self.download_dir}"
        )


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Download lab result files from wyniki.diag.pl."
    )
    parser.add_argument(
        "--interactive-browser",
        action="store_true",
        help="Open a visible browser, wait for manual login/page prep, then crawl.",
    )
    parser.add_argument(
        "--cdp-url",
        default=os.getenv("WYNIKI_CDP_URL"),
        help="Attach to an already-running browser over Chrome DevTools Protocol.",
    )
    parser.add_argument(
        "--ignore-incapsula",
        action="store_true",
        help="Skip Incapsula block-page detection. Useful with prepared browser sessions.",
    )
    parser.add_argument(
        "--profile-dir",
        default=os.getenv("WYNIKI_PROFILE_DIR", ".playwright/wyniki-profile"),
        help="Persistent browser profile directory.",
    )
    parser.add_argument(
        "--download-dir",
        default=os.getenv("WYNIKI_DOWNLOAD_DIR", "downloads/xml_results"),
        help="Directory for downloaded XML, PDF, and CSV files.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run the normal persistent browser in headless mode.",
    )
    parser.add_argument(
        "--remote-debugging-port",
        type=int,
        default=int(os.getenv("WYNIKI_REMOTE_DEBUGGING_PORT", "9222")),
        help="Remote debugging port used by --interactive-browser.",
    )
    args = parser.parse_args()

    # Load environment variables
    load_dotenv("tests/.env")

    username = os.getenv("WYNIKI_USERNAME")
    password = os.getenv("WYNIKI_PASSWORD")

    if not username or not password:
        raise ValueError(
            "WYNIKI_USERNAME and WYNIKI_PASSWORD must be set in tests/.env file"
        )

    env_headless = os.getenv("WYNIKI_HEADLESS", "").lower() in {"1", "true", "yes"}
    env_ignore_incapsula = os.getenv("WYNIKI_IGNORE_INCAPSULA", "").lower() in {
        "1",
        "true",
        "yes",
    }
    env_interactive_browser = os.getenv("WYNIKI_INTERACTIVE_BROWSER", "").lower() in {
        "1",
        "true",
        "yes",
    }

    # Create crawler and run
    crawler = WynikiCrawler(
        username,
        password,
        download_dir=args.download_dir,
        profile_dir=args.profile_dir,
        headless=args.headless or env_headless,
        cdp_url=args.cdp_url,
        ignore_incapsula=args.ignore_incapsula or env_ignore_incapsula,
        interactive_browser=args.interactive_browser or env_interactive_browser,
        remote_debugging_port=args.remote_debugging_port,
    )
    await crawler.crawl()


if __name__ == "__main__":
    asyncio.run(main())
