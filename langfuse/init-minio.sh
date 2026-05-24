#!/bin/sh
# Wait for MinIO to be ready
until mc alias set myminio http://langfuse-minio:9000 "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" 2>/dev/null; do
  echo "Waiting for MinIO..."
  sleep 2
done

# Create buckets if they don't exist
mc mb --ignore-existing myminio/langfuse
mc mb --ignore-existing myminio/langfuse-media

echo "MinIO buckets ready."
