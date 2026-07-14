"""Single entrypoint: `slack <command>` instead of `python -m slack_msg_reader....`."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import click

from slack_msg_reader import export as export_module
from slack_msg_reader import report as report_module
from slack_msg_reader.analysis.cli import cli as analyze_cli
from slack_msg_reader.collect import cli as collect_cli
from slack_msg_reader.config import DATA_DIR


def _this_week_range() -> tuple[datetime, datetime]:
    """Monday 00:00 through right now, both UTC."""
    now = datetime.now(timezone.utc)
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday, now


@click.group()
def cli():
    """Slack message archiver & analyzer (slack init / inspect / collect / analyze ...)."""


for name, cmd in collect_cli.commands.items():
    cli.add_command(cmd, name=name)

cli.add_command(analyze_cli, name="analyze")


@cli.command()
@click.option("--channel", default=None, help="Restrict to one channel name.")
@click.option("--user", default=None, help="Restrict to one sender's display name.")
@click.option(
    "--since", type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="Only messages on/after this date (YYYY-MM-DD)."
)
@click.option(
    "--until", type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="Only messages on/before this date (YYYY-MM-DD, inclusive)."
)
@click.option(
    "--max-chars",
    default=export_module.DEFAULT_MAX_CHARS,
    show_default=True,
    help="Target per-file character budget.",
)
@click.option(
    "--max-files",
    default=export_module.DEFAULT_MAX_FILES,
    show_default=True,
    help="Hard cap on number of output files (per-file budget grows to fit this if needed).",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=DATA_DIR / "exports",
    show_default=True,
    help="Directory to write the Markdown file(s) to.",
)
def export(channel, user, since, until, max_chars, max_files, output_dir):
    """Export archived messages as AI-friendly Markdown, filtered and grouped by channel.

    Ideally produces a single file; splits into up to --max-files only when
    the content exceeds --max-chars, so it fits within a target model's
    context window.
    """
    since_utc = since.replace(tzinfo=timezone.utc) if since else None
    until_utc = (until + timedelta(days=1, microseconds=-1)).replace(tzinfo=timezone.utc) if until else None

    paths, truncated = export_module.write_export(
        output_dir,
        channel=channel,
        user=user,
        since=since_utc,
        until=until_utc,
        max_chars=max_chars,
        max_files=max_files,
    )
    if not paths:
        click.echo("No messages matched the given filters.")
        return

    for p in paths:
        click.echo(f"Wrote {p} ({p.stat().st_size:,} bytes)")
    if truncated:
        click.echo(
            f"Warning: content still exceeds {max_files} files even after growing the per-file budget; "
            "increase --max-files or narrow the filters."
        )


@cli.command()
@click.option("--user", "participant", required=True, help="Participant to center the report on (display name).")
@click.option(
    "--since", type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="Only messages on/after this date (YYYY-MM-DD)."
)
@click.option(
    "--until", type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="Only messages on/before this date (YYYY-MM-DD, inclusive)."
)
@click.option("--this-week", is_flag=True, help="Shortcut for --since/--until covering Monday through now.")
@click.option(
    "--max-chars",
    default=export_module.DEFAULT_MAX_CHARS,
    show_default=True,
    help="Target per-file character budget.",
)
@click.option(
    "--max-files",
    default=export_module.DEFAULT_MAX_FILES,
    show_default=True,
    help="Hard cap on number of output files (per-file budget grows to fit this if needed).",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=DATA_DIR / "reports",
    show_default=True,
    help="Directory to write the conversation export + analysis prompt to.",
)
def report(participant, since, until, this_week, max_chars, max_files, output_dir):
    """Full-context conversation export for one person, plus an AI analysis prompt.

    Exports every message (from anyone, not just --user) in every channel/DM
    where that person posted during the window, so the exchange makes sense
    on its own -- then writes a companion report_prompt.txt covering what
    they did, new tasks and deadlines, poor communication, and anything left
    unanswered. This tool does not call any AI itself: paste both files into
    whatever chatbot you use.
    """
    if this_week:
        since_utc, until_utc = _this_week_range()
    else:
        since_utc = since.replace(tzinfo=timezone.utc) if since else None
        until_utc = (until + timedelta(days=1, microseconds=-1)).replace(tzinfo=timezone.utc) if until else None

    result = report_module.generate_report(
        output_dir,
        participant=participant,
        since=since_utc,
        until=until_utc,
        max_chars=max_chars,
        max_files=max_files,
    )
    if not result.conversation_files:
        click.echo(f"No messages found for '{participant}' in the given window.")
        return

    for p in result.conversation_files:
        click.echo(f"Wrote {p} ({p.stat().st_size:,} bytes)")
    click.echo(f"Wrote {result.prompt_file}")
    if result.truncated:
        click.echo(
            f"Warning: content still exceeds {max_files} files even after growing the per-file budget; "
            "increase --max-files or narrow the date range."
        )


if __name__ == "__main__":
    cli()
