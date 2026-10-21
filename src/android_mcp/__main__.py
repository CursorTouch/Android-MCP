"""Command line: ``android-mcp-beta`` starts the server on stdio."""

import os

import click

from android_mcp.server import build_server, resolve_preference
from android_mcp.server.config import CONNECTIONS


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--device", metavar="SERIAL", help="ADB device serial, or host:port.")
@click.option(
    "--connection",
    "--transport",
    "connection",
    type=click.Choice(CONNECTIONS, case_sensitive=False),
    help="How to pick a device when none is named: auto (a physical device, else an emulator), "
    "usb, or wifi.",
)
@click.option(
    "--wifi",
    metavar="HOST",
    is_flag=False,
    flag_value="",
    default=None,
    help="Use ADB over Wi-Fi. HOST or HOST:PORT (port 5555 if omitted); without a value, "
    "ANDROID_MCP_HOST is used.",
)
@click.option(
    "--usb",
    metavar="SERIAL",
    is_flag=False,
    flag_value="",
    default=None,
    help="Use ADB over USB. Optionally a specific serial.",
)
def main(device: str | None, connection: str | None, wifi: str | None, usb: str | None) -> None:
    """Android MCP server: lets an AI agent operate an Android device over ADB.

    The device is connected on first use, so the server starts whether or not one is attached.
    Without options it uses the first physical device, or an emulator when there is none. The
    environment variables ANDROID_MCP_DEVICE, ANDROID_MCP_CONNECTION and ANDROID_MCP_HOST set
    the same things as the options, which win when both are given; ANDROID_MCP_ADB_PATH names
    the adb binary; SCREENSHOT_QUANTIZED=true makes screenshots smaller.
    """
    try:
        preference = resolve_preference(
            device=device, connection=connection, wifi=wifi, usb=usb, env=os.environ
        )
    except ValueError as error:
        raise click.UsageError(str(error)) from error
    build_server(preference).run()


if __name__ == "__main__":
    main()
