__DOMAIN__ {
    encode gzip
    reverse_proxy /storage/v1/chunks/* unix//dev/shm/xrxh.socket
    respond / 410
}
