# Helper script to synchronize or archive the X12-to-JSON parser project files
# using paths relative to the project root directory.
set -euo pipefail

SCRIPT_DIR="$(dirname "${BASH_SOURCE[0]}")"
cd "$SCRIPT_DIR/.."

DEST_DIR="${1:-.}"

if [ "$DEST_DIR" = "." ]; then
    echo "Project root verified at relative path: ."
else
    echo "Synchronizing project files to: $DEST_DIR"
    mkdir -p "$DEST_DIR"
    cp -r ./LICENSE ./README.md ./DESIGN.md ./prd.md ./requirements.txt ./setup.py ./dashboard.html ./docs ./sample_data ./scripts ./skills ./tests ./x12_parser "$DEST_DIR"/
    echo "Files synchronized to: $DEST_DIR"
fi

ARCHIVE_PATH="dist/x12-to-json-parser-export.tar.gz"
mkdir -p "dist"
tar --exclude='./dist' --exclude='./.git' --exclude='__pycache__' -czf "$ARCHIVE_PATH" .
echo "Standalone archive generated at: $ARCHIVE_PATH"
