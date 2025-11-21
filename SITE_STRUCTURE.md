# Wyniki.diag.pl Site Structure

This document describes the structure of the wyniki.diag.pl website as discovered using the Playwright MCP server.

## Overview

- **Type**: Single Page Application (SPA) built with React
- **UI Framework**: Material-UI (MUI)
- **Base URL**: https://wyniki.diag.pl

## Authentication Flow

### Login Page (`/`)

The site presents two login options:

1. **Single Order Access** (left panel)
   - For accessing results with just an order number
   - Fields:
     - Order number: `input[name="orderNumber"]`
     - Birth date: `input[name="birthDate"]`
   - Submit: `button[data-cy="submit-single-order-btn"]`

2. **Regular Customer Account** (right panel) - **Used by our crawler**
   - For customers with Karta Stałego Klienta
   - Fields:
     - PESEL or card number: `input[name="accountId"]`
     - Password: `input[name="password"]`
   - Submit: `button[data-cy="submit-account-btn"]`

### Post-Login

After successful login, redirects to `/zlecenia` (orders list)

## Orders List Page (`/zlecenia`)

### Structure
- Lists all blood test orders in chronological order
- Supports pagination (multiple pages of results)
- Each order card displays:
  - Date of registration
  - Order number (with barcode visualization)
  - List of tests performed
  - Location/facility name (when available)

### Key Selectors
- Order cards: `div.MuiPaper-root` with `data-cy="view-result-btn"`
- View results button: `a[data-cy="view-result-btn"]`
- Pagination:
  - Next page: `button[data-cy="pagination-next"]`
  - Previous page: `button[data-cy="pagination-previous"]`
  - First page: `button[data-cy="pagination-first"]`
  - Last page: `button[data-cy="pagination-last"]`

### Example Order Card Structure
```html
<div class="MuiPaper-root">
  <p class="MuiTypography-h5">26 kwietnia 2025</p>
  <div>
    <svg><!-- barcode --></svg>
    <p>402337694L</p>
  </div>
  <p>ALT, AST, Bilirubina całkowita, ...</p>
  <p>31-864 Kraków, ul. prof. M. Życzkowskiego 16</p>
  <a data-cy="view-result-btn" href="/zlecenie/...">Zobacz wyniki</a>
</div>
```

## Order Details Page (`/zlecenie/{encrypted_id}`)

### Structure
- Header with order information
  - Date
  - Order number (barcode format, e.g., "402337694L")
- Action buttons:
  - Share with doctor: `button[data-cy="share-results-btn"]`
  - Download results: `button[data-cy="get-tests-btn"]`
  - Create complaint: `button[data-cy="create-complaint-button"]`
  - Reorder: `button[data-cy="reorder-button"]`

### Test Results Organization
- Tests grouped by type (e.g., "Morfologia krwi", "Lipidogram")
- Quick navigation chips at top: `div[data-cy^="test-chip-"]`
- Each test section shows:
  - Test name as heading
  - Execution time information
  - Table of parameters with:
    - Parameter name
    - Result value
    - Reference range
    - Visual graph/chart
    - History button: `button[data-cy="result-history-button"]`

### Key Selectors
- Order number: `p.MuiTypography-body2` containing 'L' suffix
- Download button: `button[data-cy="get-tests-btn"]`
- Test sections: `div[id^="section-"]`
- Parameter rows: `div.MuiGrid2-root` with test data

### Example Result Structure
```html
<div class="MuiGrid2-root">
  <p>Leukocyty</p>
  <div>
    <p>4,18 tys/µl</p>
  </div>
  <div>
    <p>4 - 10</p>
  </div>
  <div><!-- graph visualization --></div>
  <button data-cy="result-history-button">Historia wyników</button>
</div>
```

## Download Mechanism

When clicking `button[data-cy="get-tests-btn"]`:
1. A dialog may appear (implementation varies)
2. Look for XML download option (exact selector TBD - may need adjustment)
3. Possible selectors to try:
   - `button:has-text('XML')`
   - `a[href*='xml']`
   - `a:has-text('XML')`

**Note**: The exact download dialog structure needs further investigation. The current implementation in the crawler attempts multiple selector strategies.

## Data Attributes

The site uses consistent data attributes for testing:
- `data-cy`: Cypress testing attributes (primary)
- `data-testid`: Additional test identifiers
- These make the site highly scrapable and maintainable

## Important Notes

1. **SPA Loading**: The site requires full JavaScript execution before inspection
   - Must wait for `networkidle` or specific selectors
   - Typical wait time: 2-3 seconds after navigation

2. **Material-UI Classes**: CSS classes are auto-generated and may change
   - Prefer data attributes over CSS class selectors
   - MUI classes like `css-xxxxx` are not stable

3. **URLs**: Order detail URLs use encrypted IDs
   - Format: `/zlecenie/{encrypted_id}`
   - Not predictable from order number
   - Must be extracted from order list links

4. **Pagination**: Orders list may span multiple pages
   - Check for enabled "next" button
   - Wait for page load after navigation

## Testing Credentials

Stored in `tests/.env`:
```
WYNIKI_USERNAME=02011762
WYNIKI_PASSWORD=ZJEng!iBgr@c3dB
```

## Browser Requirements

- Chromium-based browser (via Playwright)
- JavaScript must be enabled
- Cookies must be enabled
- Resolution: 900x600 minimum (for browser_action tool)
