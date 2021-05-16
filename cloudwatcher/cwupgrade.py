#!/usr/bin/env python3

import argparse
from io import RawIOBase
import cloudwatcher
import time


def main():
    parser = argparse.ArgumentParser(description="Upgrade CloudWatcher firmware.")
    parser.add_argument(
        "--port",
        "-p",
        metavar="port",
        type=str,
        required=True,
        help="Serial port to which a CloudWatcher is attached",
    )
    parser.add_argument(
        "--firmware",
        "-f",
        metavar="filename",
        type=argparse.FileType("rb"),
        required=True,
        help="firmware file name (.has)",
    )

    parser.add_argument(
        "--reboot-first",
        "-b",
        action="store_true",
        default=False,
        required=False,
        help="Trigger CloudWatcher reboot before upgrading",
    )

    args = parser.parse_args()

    cw = cloudwatcher.CloudWatcher(args.port)
    if args.reboot_first:
        cw.initialize()
        print(f"Current version: {cw.reboot()}")

    try:
        cw.upgrade(args.firmware.read())
    except ValueError as upgrade_issue:
        print(f"\n\nUpgrade failed: {upgrade_issue}")
        exit()
    except:
        print("\n\n")
        raise

    print(f"Upgraded to version {cw.get_version()}")


if __name__ == "__main__":
    main()
