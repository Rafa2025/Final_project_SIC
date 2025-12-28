#!/usr/bin/env bash
set -e

OUT="certs/sink"
mkdir -p "$OUT"

openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-521 \
    -out "$OUT/sink.key.pem"

openssl req -new -key "$OUT/sink.key.pem" \
    -subj "/CN=00000000000000000000000000000000/OU=Sink" \
    -out "$OUT/sink.csr.pem"

openssl x509 -req -in "$OUT/sink.csr.pem" \
    -CA certs/ca/ca.cert.pem -CAkey certs/ca/ca.key.pem -CAcreateserial \
    -out "$OUT/sink.cert.pem" -days 365 -sha512 \
    -extfile <(printf "basicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\n")

echo "Issued sink cert in $OUT"