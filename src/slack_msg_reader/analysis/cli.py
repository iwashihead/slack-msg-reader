import click
import pandas as pd

from slack_msg_reader.analysis import queries

pd.set_option("display.max_rows", 100)
pd.set_option("display.width", 120)


@click.group()
def cli():
    """Analyze the archived Slack data (run `collect` first to populate the DB)."""


@cli.command()
def channels():
    """Message count per channel."""
    click.echo(queries.messages_per_channel().to_string(index=False))


@cli.command()
@click.option("--channel", default=None, help="Restrict to one channel name.")
def users(channel):
    """Message count per user, optionally scoped to one channel."""
    click.echo(queries.messages_per_user(channel_name=channel).to_string(index=False))


@cli.command()
def hourly():
    """Message volume by hour of day (0-23, UTC)."""
    click.echo(queries.activity_by_hour().to_string(index=False))


@cli.command()
def weekday():
    """Message volume by weekday (0=Sun..6=Sat)."""
    click.echo(queries.activity_by_weekday().to_string(index=False))


@cli.command()
@click.option("--limit", default=20)
def threads(limit):
    """Messages with the most thread replies."""
    click.echo(queries.reply_thread_leaderboard(limit=limit).to_string(index=False))


@cli.command()
@click.option("--limit", default=20)
def reactions(limit):
    """Most-used reaction emoji across the archive."""
    click.echo(queries.reaction_leaderboard(limit=limit).to_string(index=False))


@cli.command()
@click.option("--top-n", default=30)
def words(top_n):
    """Naive word-frequency report (see queries.py caveat re: Japanese tokenization)."""
    click.echo(queries.top_words(top_n=top_n).to_string(index=False))


@cli.command()
@click.argument("keyword")
@click.option("--limit", default=50)
def search(keyword, limit):
    """Full-text-ish search (SQL LIKE) across all archived messages."""
    click.echo(queries.keyword_search(keyword, limit=limit).to_string(index=False))


if __name__ == "__main__":
    cli()
