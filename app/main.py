"""CLI entrypoint for email assistant."""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer

from app.graph_client import acquire_token_interactive

app = typer.Typer(help="Email Assistant Agent CLI")


@app.command()
def run() -> None:
    """Process recent emails through the pipeline."""
    from run_local import main

    raise typer.Exit(main())


@app.command()
def test() -> None:
    """Run pytest test suite."""
    result = subprocess.run(["pytest", "-v"], cwd=None)
    raise typer.Exit(result.returncode)


@app.command()
def peek(
    top: int = typer.Option(5, "--top", "-n", help="Number of recent inbox messages"),
) -> None:
    """Fetch recent emails from Graph and show pipeline readiness gaps."""
    from app.peek_inbox import peek_inbox

    raise typer.Exit(peek_inbox(top=top))


@app.command("scrape-inbox")
def scrape_inbox(
    max_pages: int = typer.Option(100, "--max-pages", help="Pages to fetch (100 msgs/page)"),
    page_size: int = typer.Option(100, "--page-size", help="Messages per page (max 100)"),
) -> None:
    """Scrape inbox history; build domain/contact catalog for categorization."""
    from app.inbox_catalog import print_scrape_summary, save_catalog
    from app.inbox_catalog import scrape_inbox as do_scrape

    typer.echo(f"Scraping inbox (up to {max_pages * page_size} messages)...")
    domains, contacts = do_scrape(max_pages=max_pages, page_size=page_size)
    save_catalog(domains, contacts)
    print_scrape_summary(domains, contacts)


@app.command("categorize-domains")
def categorize_domains_cmd() -> None:
    """Apply category rules to scraped inbox_domains.yaml."""
    from app.catalog_categorize import categorize_domains

    n = categorize_domains()
    typer.echo(
        f"Updated categories for {n} domains. Edit data/catalog/inbox_domains.yaml as needed."
    )


@app.command("apply-catalog")
def apply_catalog_cmd() -> None:
    """Apply categorized catalog → companies.yaml, vault, agent policies."""
    from app.catalog_apply import apply_catalog
    from app.catalog_categorize import categorize_domains

    if Path("data/catalog/inbox_domains.yaml").exists():
        categorize_domains()
    stats = apply_catalog()
    typer.echo("Applied catalog:")
    for k, v in stats.items():
        typer.echo(f"  {k}: {v}")
    typer.echo(
        "\nEdit data/catalog/inbox_domains.yaml to set categories, then re-run apply-catalog."
    )


@app.command()
def ui(
    host: str = typer.Option("127.0.0.1", "--host", "-h"),
    port: int = typer.Option(8080, "--port", "-p"),
    open_browser: bool = typer.Option(True, "--open/--no-open"),
) -> None:
    """Launch Email Assistant Studio web UI for catalog editing."""
    import webbrowser

    import uvicorn

    url = f"http://{host}:{port}"
    typer.echo(f"Email Assistant Studio → {url}")
    if open_browser:
        webbrowser.open(url)
    uvicorn.run("app.web.app:app", host=host, port=port, reload=False)


@app.command()
def authenticate() -> None:
    """Authenticate to Microsoft Graph via device code flow."""
    token = acquire_token_interactive()
    typer.echo(f"Authenticated successfully (token length: {len(token)})")


@app.command("sync-knowledge")
def sync_knowledge_cmd(
    max_pages: int = typer.Option(50, "--max-pages", help="Inbox pages to scan (100 msgs/page)"),
    page_size: int = typer.Option(100, "--page-size", help="Messages per page (max 100)"),
    no_recontext: bool = typer.Option(
        False, "--no-recontext", help="Skip LLM summarization for new mail"
    ),
) -> None:
    """Copy approved-domain emails into the local knowledge index."""
    import os

    from app.email_knowledge import knowledge_stats, sync_knowledge
    from app.graph_client import get_email_backend

    backend = get_email_backend()
    if os.getenv("EMAIL_BACKEND", "mock").lower() == "mock":
        typer.echo("Mock backend: syncing from fixtures only.")
        from app.email_knowledge import sync_knowledge_from_fixture
        from app.graph_client import MockGraphBackend

        emails = MockGraphBackend().list_recent_messages(top=max_pages * page_size)
        result = sync_knowledge_from_fixture(
            emails,
            recontextualize_new=not no_recontext,
        )
    else:
        result = sync_knowledge(
            backend=backend,
            max_pages=max_pages,
            page_size=page_size,
            recontextualize_new=not no_recontext,
        )
    stats = knowledge_stats()
    typer.echo(
        f"Done: scanned={result.scanned} added={result.added} "
        f"recontextualized={result.recontextualized} total_indexed={stats['entry_count']}"
    )
    if result.errors:
        typer.echo(f"Errors ({len(result.errors)}):")
        for err in result.errors[:5]:
            typer.echo(f"  {err}")


if __name__ == "__main__":
    app()
