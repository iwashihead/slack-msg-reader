import logging
from datetime import datetime, timedelta, timezone

import click

from slack_msg_reader.db import repository
from slack_msg_reader.db.database import init_db, session_scope
from slack_msg_reader.scraper import chrome_launcher
from slack_msg_reader.scraper.browser import SlackTabNotFoundError, connect_slack_page
from slack_msg_reader.scraper.channel_list import list_channels
from slack_msg_reader.scraper.message_scraper import (
    collect_channel_messages,
    current_team_id,
    datetime_to_ts,
    navigate_to_channel,
    ts_to_datetime,
)
from slack_msg_reader.util import slugify_user

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("collect")


def run_inspect() -> tuple[str, list[dict]]:
    """Attaches to the Slack tab and returns (page_url, channels). Reusable by CLI and GUI."""
    with connect_slack_page() as page:
        return page.url, list_channels(page)


def run_collect(
    kind: str = "all",
    name_contains: str | None = None,
    full_history: bool = False,
    channel_ids: list[str] | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    collect_threads: bool = True,
) -> int:
    """Runs one full collection pass. Returns the number of channels visited.

    Shared by the CLI `collect` command and the GUI's Collect tab -- progress
    is reported purely through the `collect` logger (attach a handler to see it),
    not return values, so both callers get identical behavior.

    `channel_ids`, when given, restricts collection to exactly those channel
    ids (as returned by list_channels/inspect), overriding kind/name_contains.
    `since`/`until` bound the collected date range independently of what's
    already stored -- useful to cap how far back a first-time collect walks
    on a very active channel, or to backfill/export just one period.
    """
    init_db()
    since_ts = datetime_to_ts(since) if since else None
    until_ts = datetime_to_ts(until) if until else None

    with connect_slack_page() as page:
        team_id = current_team_id(page)
        channels = list_channels(page)

        if channel_ids:
            wanted = set(channel_ids)
            channels = [c for c in channels if c["id"] in wanted]
        else:
            if kind != "all":
                channels = [c for c in channels if c["kind"] == kind]
            if name_contains:
                needle = name_contains.lower()
                channels = [c for c in channels if needle in c["name"].lower()]

        log.info("Collecting from %d channel(s)...", len(channels))

        for ch in channels:
            log.info("Channel: [%s] %s (%s)", ch["kind"], ch["name"], ch["id"])

            with session_scope() as session:
                repository.upsert_channel(session, ch["id"], ch["name"], ch["kind"])
                last_ts = None if full_history else repository.latest_ts_for_channel(session, ch["id"])
                seed = None if full_history else repository.latest_message_sender(session, ch["id"])
                seed_sender, seed_sender_id = seed if seed else (None, None)

            try:
                navigate_to_channel(page, team_id, ch["id"])
            except Exception:
                log.exception("Failed to open channel %s, skipping", ch["id"])
                continue

            messages = collect_channel_messages(
                page,
                last_ts,
                seed_sender=seed_sender,
                seed_sender_id=seed_sender_id,
                since_ts=since_ts,
                until_ts=until_ts,
                collect_threads=collect_threads,
            )
            log.info("  -> %d new message(s)", len(messages))
            if not messages:
                continue

            with session_scope() as session:
                for m in messages:
                    if repository.message_exists(session, ch["id"], m["ts"]):
                        continue
                    # Real Slack user id when we have it (works even for grouped
                    # messages via forward-fill, and for bots like Slackbot) --
                    # falls back to a name-derived slug only if truly missing,
                    # so identity doesn't shatter across a display-name change.
                    user_id = m["sender_id"] or slugify_user(m["sender"])
                    repository.upsert_user(session, user_id, m["sender"])
                    repository.insert_message(
                        session,
                        channel_id=ch["id"],
                        ts=m["ts"],
                        user_id=user_id,
                        text=m["text"],
                        thread_ts=m["thread_ts"],
                        is_thread_parent=m["reply_count"] > 0,
                        reply_count=m["reply_count"],
                        posted_at=ts_to_datetime(m["ts"]),
                        reactions=m["reactions"],
                    )

        return len(channels)


@click.group()
def cli():
    """Slack message archiver: attaches to an already-logged-in browser tab,
    no Slack App/Bot/OAuth involved."""


@cli.command()
def init():
    """Create the SQLite schema."""
    init_db()
    click.echo("DB initialized.")


@cli.command()
def chrome():
    """Start (or reuse) the dedicated Chrome used for collection.

    Runs alongside your everyday Chrome without disturbing it. Uses a
    persistent profile under ~/.slack-msg-reader/chrome-profile, so you only
    need to log into Slack manually the first time you run this.
    """
    try:
        ready = chrome_launcher.launch()
    except chrome_launcher.ChromeNotFoundError as e:
        raise click.ClickException(str(e))

    if not ready:
        raise click.ClickException(
            "Chrome started but the remote debugging port never came up. Check that no other "
            "process is already using it, then try again."
        )
    click.echo(
        "Chrome is ready. If this is the first run, log into Slack manually in the window that "
        "opened, then leave it open and run `slack inspect` or `slack collect`."
    )


@cli.command(name="inspect")
def inspect_cmd():
    """Calibration helper: confirms the DOM selectors still match your Slack tab."""
    try:
        url, channels = run_inspect()
    except SlackTabNotFoundError as e:
        raise click.ClickException(str(e))

    click.echo(f"Attached to: {url}")
    click.echo(f"Sidebar channels found: {len(channels)}")
    for ch in channels:
        click.echo(f"  - [{ch['kind']}] {ch['id']}  {ch['name']}")
    if not channels:
        click.echo(
            "No channels matched. Selectors in scraper/selectors.py likely need "
            "updating for your Slack version -- inspect the sidebar in Chrome DevTools."
        )


@cli.command()
@click.option(
    "--kind",
    type=click.Choice(["channel", "dm", "all"]),
    default="all",
    help="Restrict to channels, DMs/mpims, or all. Ignored if --channel-id is given.",
)
@click.option("--name-contains", default=None, help="Only collect channels whose name contains this substring.")
@click.option(
    "--channel-id",
    "channel_ids",
    multiple=True,
    help="Collect only this channel id (from `slack inspect`). Repeatable to select several.",
)
@click.option(
    "--full-history/--incremental",
    default=False,
    help="Ignore already-stored messages and re-walk each channel's full history.",
)
@click.option(
    "--since", type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="Don't collect messages before this date (YYYY-MM-DD)."
)
@click.option(
    "--until", type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="Don't collect messages after this date (YYYY-MM-DD, inclusive)."
)
@click.option(
    "--threads/--no-threads",
    default=True,
    help="Also open and collect each message's thread replies (slower; disable for a quick pass).",
)
def collect(kind, name_contains, channel_ids, full_history, since, until, threads):
    """Scrape visible channels/DMs and store new messages in the SQLite DB."""
    until_inclusive = (until + timedelta(days=1, microseconds=-1)).replace(tzinfo=timezone.utc) if until else None
    since_utc = since.replace(tzinfo=timezone.utc) if since else None

    try:
        run_collect(
            kind=kind,
            name_contains=name_contains,
            full_history=full_history,
            channel_ids=list(channel_ids) or None,
            since=since_utc,
            until=until_inclusive,
            collect_threads=threads,
        )
    except SlackTabNotFoundError as e:
        raise click.ClickException(str(e))

    click.echo("Done.")


if __name__ == "__main__":
    cli()
