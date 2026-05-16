import os
import zipfile
import shutil
from pathlib import Path
from fnmatch import fnmatch
import subprocess
import sys
import platform

import requests


def download_repo_zip(user, repo, branch='main'):
    url = f'https://github.com/{user}/{repo}/archive/refs/heads/{branch}.zip'
    zip_path = f'{repo}.zip'
    final_path = Path(f'./{repo}')

    if final_path.exists():
        print(f"Removing existing folder {final_path}...")
        shutil.rmtree(final_path)

    print(f"Downloading {url}...")
    r = requests.get(url)
    r.raise_for_status()

    with open(zip_path, 'wb') as f:
        f.write(r.content)

    print(f"Extracting {zip_path}...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall('.')

    os.remove(zip_path)

    inner_root = next(Path('.').glob(f"{repo}-*"))
    shutil.move(str(inner_root), final_path)

    print(f"Repository extracted to {final_path}/")
    return str(final_path)


def parse_gitignore(gitignore_path):
    patterns = []
    if os.path.exists(gitignore_path):
        with open(gitignore_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    patterns.append(line)
    return patterns


def should_ignore(filepath, patterns):
    for pattern in patterns:
        if fnmatch(filepath, pattern) or fnmatch(Path(filepath).name, pattern):
            return True
    return False


def remove_gitignored_files(base_dir, patterns):
    for root, dirs, files in os.walk(base_dir, topdown=False):
        for name in files:
            rel_path = os.path.relpath(os.path.join(root, name), base_dir)
            if should_ignore(rel_path, patterns):
                os.remove(os.path.join(root, name))

        for name in dirs:
            dir_path = os.path.join(root, name)
            if not os.listdir(dir_path):
                os.rmdir(dir_path)


def run_python_file(file_path):
    print(f"Running {file_path}...")

    if platform.system() == "Windows":
        subprocess.run([sys.executable, file_path], check=True)
    else:
        subprocess.run(["python3", file_path], check=True)

    print("Finished running script.")


user = 'benstocker07'
repo = 'SSC-Tracker-Euroscope'
branch = 'main'


dest_dir = download_repo_zip(user, repo, branch)

gitignore_path = os.path.join(dest_dir, '.gitignore')
patterns = parse_gitignore(gitignore_path)
remove_gitignored_files(dest_dir, patterns)

entry_file = os.path.join(dest_dir, 'Radar.py')

if os.path.exists(entry_file):
    run_python_file(entry_file)
else:
    print(f"Error: {entry_file} not found.")
