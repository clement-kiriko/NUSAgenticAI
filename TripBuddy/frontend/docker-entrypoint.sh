#!/bin/sh
set -e
# Substitute only ${API_UPSTREAM} — all nginx variables ($host, $uri, etc.) are left intact.
envsubst '${API_UPSTREAM}' \
    < /etc/nginx/conf.d/default.conf.template \
    > /etc/nginx/conf.d/default.conf
exec nginx -g 'daemon off;'
