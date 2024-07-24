#!/bin/sh


# Exit on error
set -e

# Save doc embeddings to chroma db
echo "Saving doc embeddings to chroma db"

cd db
python3 vector_store.py --create_db true

cd ..

# Start Gunicorn server
exec "$@"