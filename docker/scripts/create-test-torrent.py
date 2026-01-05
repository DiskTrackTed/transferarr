#!/usr/bin/env python3
"""
Generate test torrents with specified characteristics.

Creates random content files, generates .torrent file pointing to local tracker,
and optionally adds to Deluge for seeding.

Usage:
    # Basic usage - creates 50MB test torrent
    ./create-test-torrent.py --name "Test.Movie.2024"
    
    # Larger torrent
    ./create-test-torrent.py --name "Test.Movie.2024.1080p" --size 500
    
    # Multi-file torrent
    ./create-test-torrent.py --name "Test.Series.S01E01" --size 100 --files 3
    
    # Add to Deluge watch folder for immediate seeding
    ./create-test-torrent.py --name "Test.Movie.2024" --add-to-deluge

Requirements:
    pip install torf

Environment:
    TRACKER_URL - Tracker announce URL (default: http://tracker:6969/announce)
    CONTENT_DIR - Where to create content files (default: /downloads)
    TORRENT_DIR - Where to save .torrent files (default: /torrents)
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

try:
    from torf import Torrent
except ImportError:
    print("ERROR: torf library not installed. Run: pip install torf")
    sys.exit(1)


def create_random_content(output_dir: Path, name: str, size_mb: int, file_count: int = 1) -> Path:
    """
    Create random file(s) of specified total size.
    
    Args:
        output_dir: Base directory for content
        name: Torrent name (becomes directory name)
        size_mb: Total size in megabytes
        file_count: Number of files to split content into
    
    Returns:
        Path to content directory
    """
    content_dir = output_dir / name
    content_dir.mkdir(parents=True, exist_ok=True)
    
    size_per_file = (size_mb * 1024 * 1024) // file_count
    
    for i in range(file_count):
        if file_count == 1:
            filename = f"{name}.mkv"
        else:
            filename = f"{name}.part{i+1:03d}.mkv"
        
        file_path = content_dir / filename
        
        # Write random bytes in chunks to avoid memory issues
        with open(file_path, 'wb') as f:
            remaining = size_per_file
            while remaining > 0:
                chunk_size = min(remaining, 1024 * 1024)  # 1MB chunks
                f.write(os.urandom(chunk_size))
                remaining -= chunk_size
        
        actual_size_mb = file_path.stat().st_size / 1024 / 1024
        print(f"  Created: {file_path.name} ({actual_size_mb:.1f}MB)")
    
    return content_dir


def create_torrent_file(content_path: Path, tracker_url: str, output_path: Path) -> str:
    """
    Generate .torrent file for content.
    
    Args:
        content_path: Path to content (file or directory)
        tracker_url: Tracker announce URL
        output_path: Where to save .torrent file
    
    Returns:
        Info hash of generated torrent
    """
    t = Torrent(
        path=content_path,
        trackers=[tracker_url],
        private=False,
        comment="Test torrent for Transferarr testing"
    )
    t.generate()
    t.write(output_path)
    
    return t.infohash


def main():
    parser = argparse.ArgumentParser(
        description='Generate test torrents for Transferarr testing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --name "Test.Movie.2024"
  %(prog)s --name "Test.Movie.2024.1080p" --size 500
  %(prog)s --name "Test.Series.S01E01" --files 3
  %(prog)s --name "Test.Movie.2024" --add-to-deluge
        """
    )
    
    parser.add_argument(
        '--name', 
        required=True, 
        help='Torrent name (e.g., "Test.Movie.2024")'
    )
    parser.add_argument(
        '--size', 
        type=int, 
        default=50, 
        help='Total size in MB (default: 50)'
    )
    parser.add_argument(
        '--files', 
        type=int, 
        default=1, 
        help='Number of files to create (default: 1)'
    )
    parser.add_argument(
        '--tracker', 
        default=os.environ.get('TRACKER_URL', 'http://tracker:6969/announce'),
        help='Tracker announce URL'
    )
    parser.add_argument(
        '--content-dir', 
        default=os.environ.get('CONTENT_DIR', '/downloads'),
        help='Directory to create content in'
    )
    parser.add_argument(
        '--torrent-dir', 
        default=os.environ.get('TORRENT_DIR', '/torrents'),
        help='Directory to save .torrent files'
    )
    parser.add_argument(
        '--add-to-deluge', 
        action='store_true',
        help='Copy .torrent to Deluge watch folder for seeding'
    )
    parser.add_argument(
        '--deluge-watch-dir',
        default='/config/watch',
        help='Deluge watch folder path (default: /config/watch)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite existing content and torrent'
    )
    
    args = parser.parse_args()
    
    content_dir = Path(args.content_dir)
    torrent_dir = Path(args.torrent_dir)
    
    # Check if content already exists
    target_content = content_dir / args.name
    target_torrent = torrent_dir / f"{args.name}.torrent"
    
    if target_content.exists() and not args.force:
        print(f"ERROR: Content already exists: {target_content}")
        print("       Use --force to overwrite")
        sys.exit(1)
    
    if target_torrent.exists() and not args.force:
        print(f"ERROR: Torrent already exists: {target_torrent}")
        print("       Use --force to overwrite")
        sys.exit(1)
    
    # Clean up existing if force
    if args.force:
        if target_content.exists():
            shutil.rmtree(target_content)
        if target_torrent.exists():
            target_torrent.unlink()
    
    # Ensure directories exist
    content_dir.mkdir(parents=True, exist_ok=True)
    torrent_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Creating test torrent: {args.name}")
    print(f"  Size: {args.size}MB across {args.files} file(s)")
    print(f"  Tracker: {args.tracker}")
    print()
    
    # Create content
    print("Creating content files...")
    content_path = create_random_content(content_dir, args.name, args.size, args.files)
    print()
    
    # Generate .torrent
    print("Generating .torrent file...")
    info_hash = create_torrent_file(content_path, args.tracker, target_torrent)
    print(f"  Torrent: {target_torrent}")
    print(f"  Info Hash: {info_hash}")
    print()
    
    # Optionally copy to Deluge watch folder
    if args.add_to_deluge:
        watch_dir = Path(args.deluge_watch_dir)
        watch_dir.mkdir(parents=True, exist_ok=True)
        watch_target = watch_dir / target_torrent.name
        shutil.copy(target_torrent, watch_target)
        print(f"Added to Deluge watch folder: {watch_target}")
        print()
    
    print("=" * 60)
    print(f"SUCCESS!")
    print(f"  Name: {args.name}")
    print(f"  Content: {content_path}")
    print(f"  Torrent: {target_torrent}")
    print(f"  Hash: {info_hash}")
    print("=" * 60)
    
    return info_hash


if __name__ == '__main__':
    main()
