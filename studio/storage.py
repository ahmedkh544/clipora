import os
from pathlib import Path

LOCAL_ROOT=Path(os.getenv("CLIPORA_STORAGE_ROOT", "/data" if os.name!="nt" else "studio_data"))
UPLOAD_DIR=LOCAL_ROOT/"uploads"
OUTPUT_DIR=LOCAL_ROOT/"outputs"
for d in (UPLOAD_DIR,OUTPUT_DIR): d.mkdir(parents=True,exist_ok=True)


def storage_mode():
    return "s3" if os.getenv("AWS_S3_BUCKET_NAME") and os.getenv("AWS_ENDPOINT_URL") else "local"


def object_key(job_id,name): return f"jobs/{job_id}/{Path(name).name}"


def upload_object(local_path,job_id=None,name=None):
    if storage_mode()!="s3": return str(local_path)
    import boto3
    key=object_key(job_id or "local",name or Path(local_path).name)
    s3=boto3.client("s3",endpoint_url=os.getenv("AWS_ENDPOINT_URL"),region_name=os.getenv("AWS_DEFAULT_REGION","auto"),aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"))
    s3.upload_file(str(local_path),os.environ["AWS_S3_BUCKET_NAME"],key)
    return key


def presigned_get(key,expires=3600):
    if storage_mode()!="s3": return None
    import boto3
    s3=boto3.client("s3",endpoint_url=os.getenv("AWS_ENDPOINT_URL"),region_name=os.getenv("AWS_DEFAULT_REGION","auto"),aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"))
    return s3.generate_presigned_url("get_object",Params={"Bucket":os.environ["AWS_S3_BUCKET_NAME"],"Key":key},ExpiresIn=expires)


def delete_object(key):
    if storage_mode()!="s3": return
    import boto3
    s3=boto3.client("s3",endpoint_url=os.getenv("AWS_ENDPOINT_URL"),region_name=os.getenv("AWS_DEFAULT_REGION","auto"),aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"))
    s3.delete_object(Bucket=os.environ["AWS_S3_BUCKET_NAME"],Key=key)


def cleanup_s3(max_age_hours=24):
    if storage_mode()!="s3": return 0
    import boto3,datetime
    s3=boto3.client("s3",endpoint_url=os.getenv("AWS_ENDPOINT_URL"),region_name=os.getenv("AWS_DEFAULT_REGION","auto"),aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"))
    cutoff=datetime.datetime.now(datetime.timezone.utc).timestamp(); removed=0
    page=s3.get_paginator("list_objects_v2")
    for part in page.paginate(Bucket=os.environ["AWS_S3_BUCKET_NAME"],Prefix="jobs/"):
        for obj in part.get("Contents",[]):
            if cutoff-obj["LastModified"].timestamp()>max_age_hours*3600:
                s3.delete_object(Bucket=os.environ["AWS_S3_BUCKET_NAME"],Key=obj["Key"]); removed+=1
    return removed
