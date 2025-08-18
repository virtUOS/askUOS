import glob
import os

import requests

from data_ingestion.utils import get_db_id
from src.config.core_config import settings


def upload_files_ragflow(directory, db_name, base_url=None, api_key=None):
    base_url = base_url or settings.vector_db_settings.settings.base_url
    api_key = api_key or os.getenv("RAGFLOW_API_KEY")

    headers = {"Authorization": f"Bearer {api_key}"}
    dataset_id = get_db_id(base_url, db_name, headers)

    url = f"{base_url}/api/v1/datasets/{dataset_id}/documents"

    # Get all files from the directory
    file_pattern = os.path.join(directory, "*")
    file_paths = glob.glob(file_pattern)

    # Prepare files for upload
    files = []
    for file_path in file_paths:
        if os.path.isfile(file_path):
            files.append(("file", open(file_path, "rb")))

    try:
        response = requests.post(url, headers=headers, files=files)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error uploading files: {e}")
        return None
    finally:
        # Close all file handles
        for _, file_handle in files:
            file_handle.close()


def main():
    # directory = "/app/data_ingestion/faqs_output_md"
    directory = "/app/data/documents"
    db_name = "examination_regulations"
    upload_files_ragflow(directory, db_name)
    print(f"Files from {directory} uploaded to RAGFlow database '{db_name}'.")


if __name__ == "__main__":
    main()
