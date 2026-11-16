# Network and VPN configuration

## Topology

```
Hospital LAN 192.168.1.0/24                          Internet
 PCs ──HTTPS 443──► hospital server 192.168.1.10      cloud VPS (public IP)
                    wg0 10.8.0.2 ═══ WireGuard UDP 51820 ═══ wg0 10.8.0.1
                    API :8000 bound to 10.8.0.2              API :8000 bound to 10.8.0.1
```

* The **hospital initiates** the tunnel with outbound UDP and keeps it alive with `PersistentKeepalive`. **No inbound port** is opened on the hospital router.
* The cloud gateway reaches the hospital API only at `http://10.8.0.2:8000`, and the hospital reaches the cloud API at `http://10.8.0.1:8000`.
* Tunnel traffic is encrypted by WireGuard and also HMAC-signed by the application (`SYNC_SHARED_SECRET`).
* PostgreSQL has **no published ports** on either server, and Nginx answers 404 for `/api/internal/*` publicly.

## Keys and configuration

```bash
umask 077; cd /etc/wireguard
wg genkey | tee private.key | wg pubkey > public.key     # on each server
wg genpsk > psk.key                                      # once, copy to both
```

Fill in `deploy/wireguard/wg0.cloud.conf.example` and `deploy/wireguard/wg0.hospital.conf.example`, and save each as `/etc/wireguard/wg0.conf` on the matching server. Then:

```bash
sudo systemctl enable --now wg-quick@wg0
sudo wg show                                   # "latest handshake" must be recent
ping -c3 10.8.0.1                              # from the hospital
curl -s http://10.8.0.1:8000/api/health        # from the hospital, once the cloud stack is up
```

## Firewall

**Cloud:**

```bash
sudo ufw allow 443/tcp; sudo ufw allow 80/tcp; sudo ufw allow 51820/udp; sudo ufw allow OpenSSH
```

**Hospital:**

```bash
sudo ufw default deny incoming
sudo ufw allow from 192.168.1.0/24 to any port 443 proto tcp
sudo ufw allow from 192.168.1.0/24 to any port 80 proto tcp
sudo ufw allow from 192.168.1.0/24 to any port 22 proto tcp
sudo ufw enable
```

Docker-published ports bypass ufw's INPUT rules. What actually keeps port 8000 private is that the Compose files publish it only on `WG_ADDRESS`, the tunnel IP. Never set `WG_ADDRESS` to `0.0.0.0`.

## Failure behaviour

| Situation | Hospital | Remote users |
|---|---|---|
| Internet down at hospital | Full billing, offline login for verified users, alerts; events queue | Read-only replica, "live billing unavailable", last sync time shown |
| Cloud VPS down | Same as above | Cloud app unavailable |
| Hospital server down | Terminals stop (central server); UPS protects it | Read-only replica |
| Tunnel restored | Queue drains automatically (backoff ≤ 60 s) | Live operations resume |

## Clock synchronisation

Both servers must run NTP. Peer requests with a timestamp more than 300 seconds off are rejected (`PEER_UNAUTHORIZED`), and the Sync monitor shows the error.
