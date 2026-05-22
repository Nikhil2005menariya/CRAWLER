# TASK 1 — Web Crawler (LangGraph-Integrated)

## Objective
Crawl myklaticrete.com via the `crawl_node` in the LangGraph ingestion pipeline.
Output: `CrawlRecord` list stored in `IngestionState["crawl_records"]`.

## How it fits in LangGraph

```
crawl_node is the FIRST node in the ingestion_graph.
It receives IngestionState with urls_to_crawl and populates crawl_records.
The route_node then checks for changes before proceeding to parse_node.
```

## Seed URLs (50+) — `config/seed_urls.py`

```python
SEED_URLS = [
    # Product Categories (13)
    "https://myklaticrete.com/products/tile-adhesive/",
    "https://myklaticrete.com/products/specialty-adhesive/",
    "https://myklaticrete.com/products/stone-adhesives/",
    "https://myklaticrete.com/products/epoxy-tile-grout/",
    "https://myklaticrete.com/products/waterproofing/",
    "https://myklaticrete.com/products/tile-and-stone-care/",
    "https://myklaticrete.com/products/cleaning-solutions/",
    "https://myklaticrete.com/products/screed-concrete/",
    "https://myklaticrete.com/products/sound-control/",
    "https://myklaticrete.com/products/aac-block-adhesive/",
    "https://myklaticrete.com/products/3-d-printing-mortar/",
    "https://myklaticrete.com/products/cement-additive/",
    "https://myklaticrete.com/products/application-tools/",
    # Individual Products - Tile Adhesives (10)
    "https://myklaticrete.com/products/tile-adhesive/thin-set-adhesives/myk-latafix-305/",
    "https://myklaticrete.com/products/tile-adhesive/polymer-modified-thin-set-adhesives/myk-laticrete-325-high-flex/",
    "https://myklaticrete.com/products/tile-adhesive/polymer-modified-thin-set-adhesives/myk-laticrete-335-maxi/",
    "https://myklaticrete.com/products/tile-adhesive/polymer-modified-thin-set-adhesives/myk-laticrete-335-super-flex/",
    "https://myklaticrete.com/products/tile-adhesive/polymer-modified-thin-set-adhesives/myk-laticrete-345-super-flex/",
    "https://myklaticrete.com/products/tile-adhesive/thin-set-adhesives/myk-laticrete-307/",
    "https://myklaticrete.com/products/tile-adhesive/thin-set-adhesives/myk-laticrete-315-plus/",
    "https://myklaticrete.com/products/tile-adhesive/latex-fortified-thin-set-adhesives/myk-laticrete-111-4237/",
    "https://myklaticrete.com/products/tile-adhesive/latex-fortified-thin-set-adhesives/myk-laticrete-111-73/",
    "https://myklaticrete.com/products/tile-adhesive/polymer-based-adhesives/myk-laticrete-303/",
    # Specialty Adhesives (8)
    "https://myklaticrete.com/products/specialty-adhesive/myk-laticrete-dwa-215-plus/",
    "https://myklaticrete.com/products/specialty-adhesive/myk-laticrete-latapoxy-310/",
    "https://myklaticrete.com/products/specialty-adhesive/latapoxy-300/",
    "https://myklaticrete.com/products/specialty-adhesive/myk-laticrete-pua-212/",
    "https://myklaticrete.com/products/specialty-adhesive/latapoxy-fast-and-clear/",
    "https://myklaticrete.com/products/specialty-adhesive/myk-laticrete-dwa-215/",
    "https://myklaticrete.com/products/specialty-adhesive/latapoxy-standard/",
    "https://myklaticrete.com/products/specialty-adhesive/latapoxy-270/",
    # Stone (2), Grouts (7), Waterproofing (2)
    "https://myklaticrete.com/products/stone-adhesives/myk-laticrete-340-medium-bed-adhesive/",
    "https://myklaticrete.com/products/stone-adhesives/myk-laticrete-320-thick-bed-adhesive/",
    "https://myklaticrete.com/products/epoxy-tile-grout/stainfree/myk-laticrete-sp-100-tile-joint/",
    "https://myklaticrete.com/products/epoxy-tile-grout/stainfree/myk-laticrete-sp-100-duo/",
    "https://myklaticrete.com/products/epoxy-tile-grout/stainfree/myk-laticrete-sp-100-uno/",
    "https://myklaticrete.com/products/epoxy-tile-grout/stainfree/myk-laticrete-stellar-grout/",
    "https://myklaticrete.com/products/epoxy-tile-grout/cementitious/myk-laticrete-500/",
    "https://myklaticrete.com/products/epoxy-tile-grout/cementitious/myk-laticrete-600/",
    "https://myklaticrete.com/products/epoxy-tile-grout/specialty-grout/latapoxy-2000/",
    "https://myklaticrete.com/products/waterproofing/laticrete-9237/",
    "https://myklaticrete.com/products/waterproofing/myk-laticrete-hydro-ban/",
    # Downloads (TDS/MSDS)
    "https://myklaticrete.com/downloads/tds/",
    "https://myklaticrete.com/downloads/msds/",
    "https://myklaticrete.com/downloads/leaflets-brochure/",
    "https://myklaticrete.com/downloads/specifications/",
    "https://myklaticrete.com/downloads/product-catalogue/",
    # Solutions/Challenges
    "https://myklaticrete.com/solutions-by-applications/swimming-pools/",
    "https://myklaticrete.com/challenges-and-solutions/leaking-bathrooms/",
    "https://myklaticrete.com/challenges-and-solutions/tiles-on-different-substrates/",
    "https://myklaticrete.com/challenges-and-solutions/stones-tiles-fixing-on-external-facade/",
    "https://myklaticrete.com/challenges-and-solutions/laying-new-tiles-on-old-tiles/",
    # Technical Blogs
    "https://myklaticrete.com/blog/tile-adhesives-vs-cement/",
    "https://myklaticrete.com/blog/cold-weather-tiling-and-grouting/",
    "https://myklaticrete.com/blog/surface-preparation-tips-for-hot-weather-tiling/",
]
```

## Core Crawler Modules (same as before, called by crawl_node)

### `crawler/spider.py` — CrawlOrchestrator
- `crawl_batch(urls)` → returns list[CrawlRecord]
- Uses robots_handler, rate_limiter, content_detector, extractors
- Discovers PDF links on HTML pages and adds them to queue
- Computes content_hash via xxhash

### `crawler/robots_handler.py`
- robots.txt only blocks `/wp-admin/` — all products crawlable

### `crawler/rate_limiter.py`
- Token bucket, 2s delay, max 4 concurrent

### `crawler/extractors/`
- `html_extractor.py`: BS4, strips nav/footer/scripts
- `pdf_extractor.py`: PyMuPDF + pdfplumber for tables
- `docx_extractor.py`: python-docx

### `crawler/storage.py`
- SQLite tables: crawl_records, crawl_history
- Stores raw text + provenance metadata

### `crawler/dedup.py`
- xxhash content comparison + ETag headers

## Deliverable Checklist
- [ ] crawl_node function works as LangGraph node
- [ ] Accepts IngestionState, returns updated state with crawl_records
- [ ] 50+ URLs crawled with provenance
- [ ] Respects robots.txt, 2s rate limit
- [ ] Routes HTML/PDF/DOCX to correct extractor
- [ ] Dedup skips unchanged pages on re-crawl
