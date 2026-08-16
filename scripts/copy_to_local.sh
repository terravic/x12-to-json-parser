#!/usr/bin/env bash
# Helper script to backup, export, or sync the X12-to-JSON parser codebase.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_DIR="${1:-$SRC_DIR}"

echo "Source Directory:      $SRC_DIR"
echo "Destination Directory: $DEST_DIR"

if [ "$SRC_DIR" = "$DEST_DIR" ]; then
    echo "Notice: Source and Destination are identical ($DEST_DIR)."
    echo "The code is already directly located in your workspace."
else
    echo "Syncing files to $DEST_DIR..."
    mkdir -p "$DEST_DIR"
    cp -r "$SRC_DIR"/* "$DEST_DIR"/
    echo "Files successfully synchronized to $DEST_DIR"
fi

# Create a standalone tarball backup in /tmp
TAR_PATH="/tmp/x12-to-json-parser-export.tar.gz"
tar -czf "$TAR_PATH" -C "$SRC_DIR" .
echo "Standalone archive package generated at: $TAR_PATH"
