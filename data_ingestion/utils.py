import requests


def get_db_id(base_url, db_name: str, headers):

    try:
        resp = requests.get(
            f"{base_url}/api/v1/datasets", params={"name": db_name}, headers=headers
        )
        if resp.status_code == 200:
            datasets = resp.json()

            return datasets["data"][0]["id"]

    except requests.RequestException as e:
        raise ValueError(f"Network error: {e}")
