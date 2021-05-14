#!/usr/bin/env python

import argparse
import cloudwatcher


def main():
    parser = argparse.ArgumentParser(description="Upgrade CloudWatcher firmware.")
    parser.add_argument(
        "--port", "-p",
        metavar="port",
        type=str,
        required=True,
        help="Serial port to which a CloudWatcher is attached",
    )
    parser.add_argument(
        "--firmware", "-f",
        metavar="filename",
        type=argparse.FileType("rb"),
        required=True,
        help="firmware file name (.has)",
    )

    parser.add_argument(
        "--reboot-first", "-b",
        action="store_true",
        default=False,
        required=False,
        help="Trigger CloudWatcher reboot before upgrading",
    )

    args = parser.parse_args()

    print(args.port)
    print(args.firmware)
    print(args.reboot_first)

    cw = cloudwatcher.CloudWatcher(args.port)
    if parser.reboot_first:
        print(f"Current version: {cw.reboot()}")
    cw.update(args.firmware.read())

if __name__ == "__main__":
    main()
