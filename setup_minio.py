import os
import sys
from minio import Minio
from minio.error import S3Error

MINIO_URL = "minio.neikoscloud.net"
ACCESS_KEY = "admin"
SECRET_KEY = "admin123"
BUCKET_NAME = "devopsproject"


client = Minio(
    MINIO_URL,
    access_key=ACCESS_KEY,
    secret_key=SECRET_KEY,
    secure=True # Tương đương https
)

def get_latest_file(prefix):
    try:
        objects = client.list_objects(BUCKET_NAME, prefix=prefix, recursive=False)
        object_list = sorted([obj.object_name for obj in objects])
        
        if not object_list:
            return None
        return object_list[-1]
    except Exception as e:
        print(f"Error listing objects: {e}")
        return None

def download_file(object_name, local_path):

    try:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        
        print(f"Downloading {object_name} to {local_path}...")
        client.fget_object(BUCKET_NAME, object_name, local_path)
        return True
    except Exception as e:
        print(f"Error downloading {object_name}: {e}")
        return False


def download_directory(minio_prefix, local_dir):

    print(f"--- [NEW] DOWNLOADING ENTIRE DIRECTORY: {minio_prefix} ---")
    try:

        objects = client.list_objects(BUCKET_NAME, prefix=minio_prefix, recursive=True)
        
        count = 0
        for obj in objects:

            if obj.object_name.endswith('/'):
                continue
                
            relative_path = obj.object_name
            local_file_path = os.path.join(".", relative_path)
            
            if download_file(obj.object_name, local_file_path):
                count += 1
        
        print(f"Successfully downloaded {count} files from {minio_prefix}")
        return True
    except Exception as e:
        print(f"Error downloading directory {minio_prefix}: {e}")
        return False

def main():
    print("--- [1 & 2] SEARCHING FOR LATEST FILES ---")
    
    data_file_path = get_latest_file("dataset_daily/")
    model_file_path = get_latest_file("current_model/")

    if not data_file_path or not model_file_path:
        print("Error: Cannot find files on MinIO.")
        objects = client.list_objects(BUCKET_NAME, recursive=False)
        for obj in objects:
            print(f"Found: {obj.object_name}")
        sys.exit(1)

    data_filename = os.path.basename(data_file_path)
    model_filename = os.path.basename(model_file_path)

    print(f"Found Data: [{data_filename}]")
    print(f"Found Model: [{model_filename}]")

    print("--- [3] DOWNLOADING ---")
    local_data = "dataset_daily/dataset.csv"
    local_model = "current_model/model.pth"

    if os.path.exists(local_data) and os.path.exists(local_model):
        print("--- [RESULT] dataset.csv and model.pth already exist. Skipping download. ---")
    else:
        success_data = download_file(data_file_path, local_data)
        success_model = download_file(model_file_path, local_model)
        
        if not success_data or not success_model:
            print("Download failed!")
            sys.exit(1)
    download_directory("dataset_test/", "./dataset_test/")

    print("--- [4] VERIFY ---")
    for path in [local_data, local_model]:
        if os.path.exists(path):
            size = os.path.getsize(path) / 1024
            print(f"{path}: {size:.2f} KB")
    if os.path.exists("dataset_test/"):
        files = os.listdir("dataset_test/")
        print(f"Files in dataset_test/: {len(files)} files found.")
    
    print("Everything is ready!")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)