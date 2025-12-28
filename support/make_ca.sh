#!/usr/bin/env bash
set -e

mkdir -p certs/ca
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-521 -out certs/ca/ca.key.pem
openssl req -x509 -new -key certs/ca/ca.key.pem -sha512 -days 3650 \
    -subj "/CN=IoT-CA" \
    -out certs/ca/ca.cert.pem
echo "CA created."
