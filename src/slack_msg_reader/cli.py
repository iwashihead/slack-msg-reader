"""Single entrypoint: `slack <command>` instead of `python -m slack_msg_reader....`."""

import click

from slack_msg_reader.analysis.cli import cli as analyze_cli
from slack_msg_reader.collect import cli as collect_cli


@click.group()
def cli():
    """Slack message archiver & analyzer (slack init / inspect / collect / analyze ...)."""


for name, cmd in collect_cli.commands.items():
    cli.add_command(cmd, name=name)

cli.add_command(analyze_cli, name="analyze")


if __name__ == "__main__":
    cli()
