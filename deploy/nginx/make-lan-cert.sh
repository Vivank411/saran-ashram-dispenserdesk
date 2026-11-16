#!/usr/bin/env bash
# Creates a private CA and a certificate for the hospital server's LAN name/IP.
# Install certs/hospital-ca.crt as a trusted root on each hospital computer (once).
# Usage: ./make-lan-cert.sh dispensary.hospital.lan 192.168.1.10
set -euo pipefail
NAME="${1:?hostname, e.g. dispensary.hospital.lan}"
IP="${2:?LAN IP of the hospital server}"
DIR="$(cd "$(dirname "$0")" && pwd)/certs"
mkdir -p "$DIR" && cd "$DIR"
umask 077
if [ ! -f hospital-ca.key ]; then
  openssl req -x509 -newkey rsa:4096 -sha256 -days 3650 -nodes -keyout hospital-ca.key -out hospital-ca.crt \
    -subj "/CN=Dispensary Desk Hospital CA"
fi
openssl req -newkey rsa:2048 -nodes -keyout privkey.pem -out server.csr -subj "/CN=${NAME}"
printf "subjectAltName=DNS:%s,IP:%s\nextendedKeyUsage=serverAuth\n" "$NAME" "$IP" > san.ext
openssl x509 -req -in server.csr -CA hospital-ca.crt -CAkey hospital-ca.key -CAcreateserial -days 825 -sha256 \
  -extfile san.ext -out server.crt
cat server.crt hospital-ca.crt > fullchain.pem
rm -f server.csr san.ext
echo "Created $DIR/fullchain.pem and privkey.pem. Distribute $DIR/hospital-ca.crt to hospital PCs."
