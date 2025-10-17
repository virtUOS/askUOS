import glob
import os

import frontmatter
import requests

from data_ingestion.utils import get_db_id
from src.config.core_config import settings


def upload_files_ragflow(
    directory, db_name, base_url=None, api_key=None, save_metadata=False
):
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


def insert_metadata_ragflow(
    directory,
    db_name,
    base_url=None,
    api_key=None,
):
    # TODO: Onls works with md files for now. Extend to other file types.
    base_url = base_url or settings.vector_db_settings.settings.base_url
    api_key = api_key or os.getenv("RAGFLOW_API_KEY")

    headers = {"Authorization": f"Bearer {api_key}"}
    dataset_id = get_db_id(base_url, db_name, headers)

    # Get all files from the directory
    file_pattern = os.path.join(directory, "*")
    file_paths = glob.glob(file_pattern)

    for file_path in file_paths:
        if os.path.isfile(file_path):
            file_name = os.path.basename(file_path)
            # get doc id
            resp = requests.get(
                f"{base_url}/api/v1/datasets/{dataset_id}/documents",
                params={
                    "name": file_name,
                },
                headers=headers,
            ).json()
            doc_id = resp["data"]["docs"][0]["id"]

            # extract metadata
            post = frontmatter.load(file_path)

            # save metadata to ragflow
            update_url = f"{base_url}/api/v1/datasets/{dataset_id}/documents/{doc_id}"
            r = requests.put(
                update_url,
                headers=headers,
                json={"meta_fields": post.metadata},
            )
            if r.status_code != 200:
                print(f"Error updating metadata for {file_name}: {r.text}")
            else:
                print(f"Metadata updated for {file_name}")


def main():
    directory = "/app/data_ingestion/faqs_output_md"
    # directory = "/app/data/documents"
    # db_name = "examination_regulations_graph"
    db_name = "faq_md"
    # upload_files_ragflow(directory, db_name, save_metadata=True)
    # print(f"Files from {directory} uploaded to RAGFlow database '{db_name}'.")
    insert_metadata_ragflow(directory, db_name)
    print("Files updated")


if __name__ == "__main__":
    main()
