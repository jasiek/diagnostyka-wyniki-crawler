# I VIBED THIS FOR TWO DOLLARS FIFTY

# Diagnostyka Wyniki Crawler

A Python-based web crawler for downloading blood test results from [wyniki.diag.pl](https://wyniki.diag.pl) as XML and PDF files.

## Features

- ✅ Automated login with two-factor authentication (2FA) support
- ✅ Pagination support - retrieves all orders across multiple pages
- ✅ Downloads all XML files for each order
- ✅ Downloads all PDF files for each order
- ✅ Downloads all CSV files (test lists) for each order
- ✅ Unique filenames for all downloaded files
- ✅ Handles multiple download links per order
- ✅ Graceful error handling and progress reporting
- ✅ Headless or visible browser mode
- ✅ Persistent browser session so cookies, 2FA state, and visited-page storage can survive between runs

## Prerequisites

- uv (Python and dependency management)
- Valid wyniki.diag.pl account credentials

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd diagnostyka-wyniki-crawler
```

2. Install dependencies:
```bash
uv sync
```

This uses the Python version pinned in `.python-version` and installs it if
needed.

3. Install Playwright browsers:
```bash
uv run playwright install chromium
```

4. Create credentials file:
```bash
cp tests/.env.example tests/.env
```

5. Edit `tests/.env` and add your credentials:
```env
WYNIKI_USERNAME=your_pesel_or_card_number
WYNIKI_PASSWORD=your_password
```

## Usage

### Basic Usage

Run the crawler to download all available blood test results:

```bash
uv run python src/wyniki_crawler.py
```

### What Happens

1. **Session check**: The script opens a persistent browser profile and checks whether it is already logged in
2. **Login**: If the saved session is missing or expired, the script navigates to wyniki.diag.pl and logs in with your credentials
3. **2FA**: If two-factor authentication is required, you'll see a prompt:
   ```
   ============================================================
   ⚠️  TWO-FACTOR AUTHENTICATION REQUIRED
   ============================================================
   Please enter the SMS code in the browser window.
   The script will continue automatically after you submit the code.
   ============================================================
   ```
   Enter the SMS code in the browser window that opens, and the script will continue automatically.

4. **Fetch Orders**: The script retrieves all order links from the orders list, handling pagination automatically

5. **Download Files**: For each order, the script:
   - Opens the order details page
   - Extracts the order number
   - Downloads all available XML files (detailed test results)
   - Downloads all available PDF files (printable reports)
   - Downloads all available CSV files (test lists)
   - Saves files as `{order_number}.xml`, `{order_number}.pdf`, and `{order_number}.csv`
   - If multiple files of the same type exist, they're numbered with type prefix: 
     - `{order_number}_xml1.xml`, `{order_number}_xml2.xml`
     - `{order_number}_pdf1.pdf`, `{order_number}_pdf2.pdf`
     - `{order_number}_csv1.csv`, `{order_number}_csv2.csv`

6. **Results**: All files are saved to `downloads/xml_results/`

### Output Example

```
Navigating to login page...
Logging in as 02011762...

============================================================
⚠️  TWO-FACTOR AUTHENTICATION REQUIRED
============================================================
Please enter the SMS code in the browser window.
The script will continue automatically after you submit the code.
============================================================

✓ Two-factor authentication completed!
Login successful!
Fetching all orders...
Found 10 orders on page 1
Moving to page 2...
Found 5 orders on page 2
No more pages.
Total orders found: 15

[1/15] Processing order...
Processing order: 383634902L
  ✓ Saved XML: 383634902L.xml
  ✓ Saved PDF: 383634902L.pdf
  ✓ Saved CSV: 383634902L.csv

[2/15] Processing order...
Processing order: 402337694L
  ✓ Saved XML: 402337694L.xml
  ✓ Saved PDF: 402337694L.pdf
  ✓ Saved CSV: 402337694L.csv

...

✓ Crawl completed! Downloaded 15 orders to downloads/xml_results
```

## Configuration

### Saved Browser Session

By default, the crawler stores its browser profile in `.playwright/wyniki-profile`.
That profile keeps cookies, local storage, IndexedDB, and similar browser state,
so after you complete login and 2FA once, later runs can usually skip the login
step until the website expires the session.

To use a different profile directory:

```env
WYNIKI_PROFILE_DIR=.playwright/my-wyniki-profile
```

If the saved session gets stuck or you want to force a fresh login, delete the
profile directory and run the crawler again.

If the site blocks fresh automated sessions, use the interactive one-command
flow. It opens the same persistent browser profile, waits while you log in or
clear the page manually, then continues the crawl after you press Enter in the
terminal:

```bash
uv run python src/wyniki_crawler.py --interactive-browser
```

If you already have a prepared Playwright browser running with remote debugging,
you can attach to it directly:

```bash
WYNIKI_CDP_URL=http://127.0.0.1:9222 WYNIKI_IGNORE_INCAPSULA=true uv run python src/wyniki_crawler.py
```

### Custom Download Directory

You can specify a custom download directory by modifying the `main()` function in `src/wyniki_crawler.py`:

```python
crawler = WynikiCrawler(username, password, download_dir="my_custom_directory")
```

### Headless Mode

To run in headless mode (no visible browser), set:

```env
WYNIKI_HEADLESS=true
```

## Project Structure

```
diagnostyka-wyniki-crawler/
├── src/
│   ├── __init__.py
│   └── wyniki_crawler.py       # Main crawler implementation
├── tests/
│   ├── __init__.py
│   └── .env                     # Credentials (gitignored)
├── downloads/
│   └── xml_results/             # Downloaded files
├── SITE_STRUCTURE.md            # Detailed site structure documentation
├── .python-version              # Python version used by uv
├── pyproject.toml               # uv project dependencies
├── uv.lock                      # Locked Python dependencies
└── README.md                    # This file
```

## XML File Format

The downloaded XML files contain structured blood test results with the following structure:

```xml
<result>
  <header>
    <patient>...</patient>
    <order>
      <barcode>383634902L</barcode>
      <created>2020-06-15 10:17:57</created>
    </order>
  </header>
  <group>
    <name>HEMATOLOGIA</name>
    <test>
      <label>Morfologia krwi (pełna)</label>
      <parameter>
        <label>Leukocyty</label>
        <value>3,82</value>
        <unit>tys/µl</unit>
        <low>4,23</low>
        <high>9,07</high>
        <flag>L</flag>
      </parameter>
      ...
    </test>
  </group>
  ...
</result>
```

## Site Structure Documentation

For detailed information about the wyniki.diag.pl website structure, including:
- Page layouts and selectors
- Authentication flow
- Download mechanisms
- Testing attributes

See [SITE_STRUCTURE.md](SITE_STRUCTURE.md)

## Troubleshooting

### "Two-factor authentication timeout"
- Ensure you enter the SMS code within 2 minutes
- Check that you're entering the correct code

### "No files downloaded"
- Some orders may not have downloadable XML/PDF files available yet
- Check the website manually to verify files are available

### "Order number shows as 'unknown'"
- The order number extraction failed
- Files will still download but with generic names
- This typically indicates a change in the website's HTML structure

### Browser doesn't open
- Ensure Playwright browsers are installed: `uv run playwright install chromium`
- Check if Chromium is properly installed in your system

## Development

### Adding New Features

The crawler uses Playwright for browser automation. Key methods:

- `login()`: Handles authentication including 2FA
- `get_all_orders()`: Retrieves all order links with pagination
- `download_order_files()`: Downloads XML and PDF files for an order
- `get_order_number_from_page()`: Extracts order number from page

### Testing

Run the crawler in visible mode (default) to watch the automation and debug issues:

```bash
uv run python src/wyniki_crawler.py
```

## License

MIT License - see LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Disclaimer

This tool is for personal use only. Ensure you have the right to access and download your medical data. Always respect the website's terms of service and rate limits.
