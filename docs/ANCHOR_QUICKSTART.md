# ANCHOR Quickstart

A short install path for new users.

## Local Machine

1. Print the exact laptop install plan:
   ```bash
   anchor install laptop
   ```
2. Follow the printed steps.
3. Open the desktop launcher or run:
   ```bash
   anchor dashboard
   ```

## Remote / Droplet

1. Print the exact droplet install plan:
   ```bash
   anchor install droplet --public-url http://<droplet-ip>:8767/anchor
   ```
2. Follow the printed steps.
3. Keep HTTPS/auth in front of the host if it is public.

## Verify

- `anchor doctor`
- `anchor status`
- `systemctl --user status anchor-web@local.service`
- `systemctl --user status anchor-web@server.service`
