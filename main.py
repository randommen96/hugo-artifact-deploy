import requests
import json
import sys
import os
from dotenv import load_dotenv
import zipfile
import shutil

load_dotenv()

METADATA_FILE = "last_downloaded_artifact.json"

def load_metadata():
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_metadata(metadata):
    with open(METADATA_FILE, 'w') as f:
        json.dump(metadata, f)

def fetch_latest_successful_run_and_artifact(owner, repo, artifact_name, github_token):
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {github_token}"
    }
    runs_url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs?per_page=1&status=completed&conclusion=success&sort=created&direction=desc"
    try:
        response = requests.get(runs_url, headers=headers)
        response.raise_for_status()
        runs_data = response.json()
        if runs_data and runs_data.get("workflow_runs"):
            latest_run = runs_data["workflow_runs"][0]
            latest_run_id = latest_run["id"]
            artifacts_url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{latest_run_id}/artifacts"
            response = requests.get(artifacts_url, headers=headers)
            response.raise_for_status()
            artifacts_data = response.json()
            if artifacts_data and artifacts_data.get("artifacts"):
                for artifact in artifacts_data["artifacts"]:
                    if artifact["name"] == artifact_name:
                        return latest_run_id, artifact
                print(f"Artifact '{artifact_name}' not found in the latest successful workflow run.")
                return latest_run_id, None
            else:
                print(f"No artifacts found for run ID {latest_run_id}.")
                return latest_run_id, None
        else:
            print("No successful workflow runs found.")
            return None, None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return None, None

def empty_directory(path):
    if os.path.exists(path):
        if os.path.isdir(path):
            print(f"Emptying directory: '{path}'...")
            for item in os.listdir(path):
                item_path = os.path.join(path, item)
                try:
                    if os.path.isfile(item_path):
                        os.unlink(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                except Exception as e:
                    print(f"Error removing item '{item_path}': {e}")
            print(f"Directory '{path}' emptied.")
            return True
        else:
            print(f"Error: '{path}' is not a directory.")
            return False
    else:
        os.makedirs(path, exist_ok=True)
        print(f"Created directory: '{path}'.")
        return True

def download_and_extract_artifact(owner, repo, artifact, github_token, output_filename, extract_path):
    if not artifact:
        return False

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {github_token}"
    }
    download_url = f"https://api.github.com/repos/{owner}/{repo}/actions/artifacts/{artifact['id']}/zip"
    try:
        response = requests.get(download_url, headers=headers, stream=True)
        response.raise_for_status()
        with open(output_filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Successfully downloaded artifact '{artifact['name']}' (ID: {artifact['id']}) to '{output_filename}'.")

        if extract_path:
            if empty_directory(extract_path):
                print(f"Extracting '{output_filename}' to '{extract_path}'...")
                try:
                    with zipfile.ZipFile(output_filename, 'r') as zip_ref:
                        zip_ref.extractall(extract_path)
                    print(f"Successfully extracted to '{extract_path}'.")
                except zipfile.BadZipFile:
                    print(f"Error: '{output_filename}' is not a valid zip file.")
                except Exception as e:
                    print(f"Error during extraction: {e}")
            else:
                print(f"Skipping extraction due to issues with the target directory: '{extract_path}'.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error downloading artifact '{artifact['name']}': {e}")
        return False

if __name__ == "__main__":
    owner = os.getenv("GITHUB_OWNER")
    repo = os.getenv("GITHUB_REPO")
    artifact_name = os.getenv("GITHUB_ARTIFACT_NAME")
    github_token = os.getenv("GITHUB_TOKEN")
    output_filename = os.getenv("OUTPUT_FILENAME", "artifact.zip")
    extract_path = os.getenv("EXTRACT_PATH")

    if not all([owner, repo, artifact_name, github_token]):
        print("Error: Please set GITHUB_OWNER, GITHUB_REPO, GITHUB_ARTIFACT_NAME, and GITHUB_TOKEN in your .env file.")
        print("Optionally, you can set OUTPUT_FILENAME and EXTRACT_PATH.")
        sys.exit(1)

    metadata = load_metadata()

    print(f"Checking artifact: '{artifact_name}'...")
    latest_run_id, latest_artifact = fetch_latest_successful_run_and_artifact(
        owner, repo, artifact_name, github_token
    )

    if latest_artifact:
        if metadata.get("run_id") != latest_run_id or metadata.get("artifact_id") != latest_artifact["id"]:
            print("Artifact has changed or not downloaded before. Downloading and extracting...")
            if download_and_extract_artifact(owner, repo, latest_artifact, github_token, output_filename, extract_path):
                metadata["run_id"] = latest_run_id
                metadata["artifact_id"] = latest_artifact["id"]
                save_metadata(metadata)
        else:
            print("Artifact has not changed since last download. Skipping download and extraction.")
    else:
        print(f"Could not find the artifact '{artifact_name}'.")

    print("\nFinished checking artifact.")
