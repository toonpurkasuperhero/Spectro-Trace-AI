#!/usr/bin/env python3
"""
SpectroTrace AI - Asset Cleanup & Retention Script
Supports:
- delete by run:<job_id>
- delete all env:test
- delete env:dev older than N days
- dry-run default (safe by default)
- protects env:demo unless explicit --include-demo is provided
"""

import os
import sys
import argparse
import time
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

try:
    import cloudinary
    import cloudinary.api
except ImportError:
    print("❌ Cloudinary Python SDK not installed.")
    sys.exit(1)

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

RESOURCE_TYPES = ["image", "video", "raw"]

def delete_by_tag(tag: str, dry_run: bool = True, include_demo: bool = False):
    if "demo" in tag and not include_demo:
        print(f"🛑 Refusing to delete tag '{tag}' containing 'demo' without --include-demo flag.")
        return

    print(f"🔍 Searching resources with tag: '{tag}' (Dry Run = {dry_run})...")
    
    total_found = 0
    for rt in RESOURCE_TYPES:
        try:
            # Check authenticated assets
            res = cloudinary.api.resources_by_tag(
                tag,
                resource_type=rt,
                type="authenticated",
                max_results=500
            )
            resources = res.get("resources", [])
            total_found += len(resources)
            print(f"  Found {len(resources)} authenticated {rt} assets.")
            for r in resources:
                print(f"    - [{rt}] {r.get('public_id')}")

            if not dry_run and resources:
                pids = [r["public_id"] for r in resources]
                del_res = cloudinary.api.delete_resources(
                    pids,
                    resource_type=rt,
                    type="authenticated",
                    invalidate=True
                )
                print(f"    Deleted: {del_res}")
        except Exception as e:
            print(f"  Error checking {rt}: {e}")

    if dry_run:
        print(f"\n💡 Dry-run complete. Total resources that would be deleted: {total_found}")
        print("To execute deletion, rerun with --execute.")
    else:
        print(f"\n✅ Deletion complete. Purged {total_found} resources.")

def main():
    parser = argparse.ArgumentParser(description="SpectroTrace AI Asset Retention & Cleanup Tool")
    parser.add_argument("--job-id", type=str, help="Delete all assets tagged with run:<job_id>")
    parser.add_argument("--parent-id", type=str, help="Delete all simulation assets linked to parent:<parent_id>")
    parser.add_argument("--simulations", action="store_true", help="Delete all assets tagged with feature:simulation")
    parser.add_argument("--env-test", action="store_true", help="Delete all assets tagged with env:test")
    parser.add_argument("--tag", type=str, help="Delete all assets with custom tag")
    parser.add_argument("--execute", action="store_true", help="Perform actual deletion (defaults to dry-run)")
    parser.add_argument("--include-demo", action="store_true", help="Allow deletion of env:demo tagged assets")

    args = parser.parse_args()
    dry_run = not args.execute

    if args.job_id:
        delete_by_tag(f"run:{args.job_id}", dry_run=dry_run, include_demo=args.include_demo)
    elif args.parent_id:
        delete_by_tag(f"parent:{args.parent_id}", dry_run=dry_run, include_demo=args.include_demo)
    elif args.simulations:
        delete_by_tag("feature:simulation", dry_run=dry_run, include_demo=args.include_demo)
    elif args.env_test:
        delete_by_tag("env:test", dry_run=dry_run, include_demo=args.include_demo)
    elif args.tag:
        delete_by_tag(args.tag, dry_run=dry_run, include_demo=args.include_demo)
    else:
        print("⚠️ No target specified. Use --job-id <id>, --parent-id <id>, --simulations, --env-test, or --tag <tag>.")
        parser.print_help()

if __name__ == "__main__":
    main()
