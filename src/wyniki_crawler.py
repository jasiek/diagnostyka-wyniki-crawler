"""
Wyniki.diag.pl crawler - retrieves blood test results as XML
"""

import os
import asyncio
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright, Page, Browser
from dotenv import load_dotenv


class WynikiCrawler:
    """Crawler for wyniki.diag.pl blood test results"""

    def __init__(self, username: str, password: str, download_dir: str = "downloads"):
        self.username = username
        self.password = password
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = "https://wyniki.diag.pl"

    async def login(self, page: Page) -> bool:
        """Log into wyniki.diag.pl"""
        print("Navigating to login page...")
        await page.goto(self.base_url, wait_until="networkidle")

        # Wait for the page to load (it's a SPA)
        await page.wait_for_timeout(2000)

        print(f"Logging in as {self.username}...")
        # Fill in the login form for "Konto Stałego Klienta"
        await page.fill("input[name='accountId']", self.username)
        await page.fill("input[name='password']", self.password)

        # Click login button
        await page.click("button[data-cy='submit-account-btn']")

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
        except:
            # If no 2FA, wait directly for orders list
            await page.wait_for_url("**/zlecenia**", timeout=10000)

        print("Login successful!")
        return True

    async def get_all_orders(self, page: Page) -> list:
        """Get all order links from the orders list page"""
        print("Fetching all orders...")

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

    async def download_order_files(self, page: Page, order_url: str, order_number: str):
        """Download all XML and PDF files for a specific order"""
        print(f"Processing order: {order_number}")

        # Navigate to order details page
        full_url = (
            f"{self.base_url}{order_url}"
            if not order_url.startswith("http")
            else order_url
        )
        await page.goto(full_url, wait_until="networkidle")

        # Wait for the page to load
        await page.wait_for_selector("button[data-cy='get-tests-btn']", timeout=5000)

        # Click the download button to open the dialog
        await page.click("button[data-cy='get-tests-btn']")

        # Wait for dialog to appear
        await page.wait_for_timeout(1500)

        # Find specific download buttons using data-cy attributes and aria-label
        xml_buttons = await page.query_selector_all(
            "button[data-cy='download-file-btn-Xml']"
        )
        pdf_buttons = await page.query_selector_all(
            "button[data-cy='download-file-btn-Pdf']"
        )
        csv_buttons = await page.query_selector_all(
            "button[aria-label='Pobierz listę badań']"
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

        # Method 3: Extract from URL path as last resort
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
            # Launch browser
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()

            try:
                # Login
                await self.login(page)

                # Get all orders
                order_urls = await self.get_all_orders(page)

                # Process each order
                for i, order_url in enumerate(order_urls, 1):
                    print(f"\n[{i}/{len(order_urls)}] Processing order...")

                    # Navigate to order page to get order number
                    full_url = (
                        f"{self.base_url}{order_url}"
                        if not order_url.startswith("http")
                        else order_url
                    )
                    await page.goto(full_url, wait_until="networkidle")

                    # Get order number (pass order_url for fallback identification)
                    order_number = await self.get_order_number_from_page(
                        page, order_url
                    )

                    # Download all files (XML, PDF, and CSV)
                    try:
                        await self.download_order_files(page, order_url, order_number)
                    except Exception as e:
                        print(f"Error downloading files for order {order_number}: {e}")
                        continue

                    # Small delay between requests
                    await page.wait_for_timeout(1000)

                print(
                    f"\n✓ Crawl completed! Downloaded {len(order_urls)} orders to {self.download_dir}"
                )

            finally:
                await browser.close()


async def main():
    """Main entry point"""
    # Load environment variables
    load_dotenv("tests/.env")

    username = os.getenv("WYNIKI_USERNAME")
    password = os.getenv("WYNIKI_PASSWORD")

    if not username or not password:
        raise ValueError(
            "WYNIKI_USERNAME and WYNIKI_PASSWORD must be set in tests/.env file"
        )

    # Create crawler and run
    crawler = WynikiCrawler(username, password, download_dir="downloads/xml_results")
    await crawler.crawl()


if __name__ == "__main__":
    asyncio.run(main())
