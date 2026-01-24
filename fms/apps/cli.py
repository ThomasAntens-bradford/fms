from fmsapps._version import version
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', action='store_true', help="Show version")
    args = parser.parse_args()
    if args.version:
        print(f"fmsapps version {version}")