#!/usr/bin/env bash
set -e

if [ $# -lt 1 ]; then
  echo "Usage: $0 <nid_hex>"
  exit 1
fi

NID_HEX=$1
OUT="certs/$NID_HEX"
mkdir -p "$OUT"

openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-521 \
    -out "$OUT/device.key.pem"

openssl req -new -key "$OUT/device.key.pem" \
    -subj "/CN=$NID_HEX/OU=IoTDevice" \
    -out "$OUT/device.csr.pem"

openssl x509 -req -in "$OUT/device.csr.pem" \
    -CA certs/ca/ca.cert.pem -CAkey certs/ca/ca.key.pem -CAcreateserial \
    -out "$OUT/device.cert.pem" -days 365 -sha512 \
    -extfile <(printf "basicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\n")

echo "Issued device cert for NID=$NID_HEX in $OUT"
