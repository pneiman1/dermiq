#!/bin/sh
# DermIQ API container entrypoint (chunk-13)
#
# Fly.io stores the Snowflake private key as a base64-encoded secret
# (SNOWFLAKE_PRIVATE_KEY_CONTENT) rather than a mounted file. Decode it to disk
# at startup, lock down permissions, point the app at it, then exec the CMD.
#
# POSIX sh (no bashisms) so this stays portable across base images.

set -e

if [ -z "$SNOWFLAKE_PRIVATE_KEY_CONTENT" ]; then
    echo "ERROR: SNOWFLAKE_PRIVATE_KEY_CONTENT is not set." >&2
    echo "       Set it with: fly secrets set SNOWFLAKE_PRIVATE_KEY_CONTENT=\"\$(base64 < rsa_key.p8)\"" >&2
    exit 1
fi

mkdir -p /secrets

echo "$SNOWFLAKE_PRIVATE_KEY_CONTENT" | base64 -d > /secrets/snowflake_rsa_key.p8
chmod 600 /secrets/snowflake_rsa_key.p8

export SNOWFLAKE_PRIVATE_KEY_PATH=/secrets/snowflake_rsa_key.p8
echo "Snowflake private key decoded to $SNOWFLAKE_PRIVATE_KEY_PATH"

exec "$@"
