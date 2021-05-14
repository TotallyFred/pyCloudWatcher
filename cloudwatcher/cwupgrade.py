#!/usr/bin/env python3

import argparse
import cloudwatcher


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

    parser.add_argument(
        "--yes-I-understand-this-program-is-broken",
        "-y",
        action="store_true",
        default=False,
        required=False,
        help="Just don't use this. This program is untested. Really.",
    )

    args = parser.parse_args()

    if not args.yes_I_understand_this_program_is_broken:
        print("Great idea - don't run this")
        exit()
    cw = cloudwatcher.CloudWatcher(args.port)
    if parser.reboot_first:
        print(f"Current version: {cw.reboot()}")
    cw.update(args.firmware.read())
    print(f"Upgraded to version {cw.get_version()}")

if __name__ == "__main__":
    main()
