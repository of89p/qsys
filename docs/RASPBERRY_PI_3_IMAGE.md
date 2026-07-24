# Raspberry Pi 3 Image Guide

Use this when one Raspberry Pi 3 already has QSys installed, tested, and
working, and you want to copy that setup onto fresh SD cards.

This image can come from a Pi that has already booted and run `systemd`. It
does not need to be a never-booted Pi. Before capturing the image, clean the
machine-specific identity so each clone can generate its own identity on first
boot.

## Hardware Rules

QSys assigns keypads from `/dev/input/by-path` by default. Those paths are tied
to the physical USB port path, so repeatability depends on hardware placement.

- Use the same Raspberry Pi 3 model and the same USB layout.
- Use the same keypad brands/models for Food, Drinks, and Chicken.
- Label the keypads and Raspberry Pi USB ports.
- Plug each keypad into the same physical USB port on every cloned Pi.
- If you ever regenerate keypad paths manually, use the same order:

```bash
cd /home/pi/qsys
python3 scripts/update_keypad_env.py --order food,drinks,chicken
sudo systemctl restart qsys-interceptor.service
```

## 1. Prepare The Source Pi

Start from a Pi 3 that is fully working:

```bash
cd /home/pi/qsys
git status
uv sync
cd frontend
pnpm install --frozen-lockfile
pnpm build
cd ..
sudo python3 scripts/install.py
```

If the keypads were already plugged into their final ports before running
`sudo python3 scripts/install.py`, `.env` has already been generated. The
installer calls `scripts/update_keypad_env.py` through
`scripts/install_systemd_services.py` unless `--skip-env` is passed.

If the keypads were plugged in later, moved, or replaced, regenerate `.env`:

```bash
python3 scripts/update_keypad_env.py --order food,drinks,chicken
sudo systemctl restart qsys-interceptor.service
```

Verify the display and services:

```bash
systemctl status qsys-server.service
systemctl status qsys-interceptor.service
ls -l /dev/input/by-path/
curl -X POST http://127.0.0.1:8080/api/v1/queue \
  -H 'Content-Type: application/json' \
  -d '{"station":"food","number":"12"}'
```

The display should show `012`.

## 2. Clean The Template Identity

Run these commands only when the source Pi is ready to become the golden image.
After this cleanup, shut the Pi down and do not boot it again before imaging. If
you do boot it again, rerun this cleanup before making the image.

If clones need to be reachable by SSH immediately, install this one-shot
first-boot helper before cleaning the template identity:

```bash
sudo tee /usr/local/sbin/qsys-firstboot-identity >/dev/null <<'EOF'
#!/bin/sh
set -eu

ssh-keygen -A

boot_hostname=""
for path in /boot/firmware/qsys-hostname /boot/qsys-hostname; do
  if [ -f "$path" ]; then
    boot_hostname="$(tr -d ' \t\r\n' < "$path")"
    break
  fi
done

case "$boot_hostname" in
  "")
    ;;
  -*|*-|*[!A-Za-z0-9-]*)
    echo "Ignoring invalid qsys-hostname: $boot_hostname" >&2
    ;;
  *)
    hostnamectl set-hostname "$boot_hostname"
    ;;
esac

mkdir -p /var/lib
touch /var/lib/qsys-firstboot-identity.done
systemctl disable qsys-firstboot-identity.service >/dev/null 2>&1 || true
EOF

sudo chmod 755 /usr/local/sbin/qsys-firstboot-identity

sudo tee /etc/systemd/system/qsys-firstboot-identity.service >/dev/null <<'EOF'
[Unit]
Description=QSys first-boot identity setup
After=local-fs.target
Before=ssh.service
ConditionPathExists=!/var/lib/qsys-firstboot-identity.done

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/qsys-firstboot-identity

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable qsys-firstboot-identity.service
```

After burning each fresh SD card, you can set that clone's hostname by writing a
plain text file named `qsys-hostname` into the SD card boot partition before the
first boot.

```bash
sudo systemctl stop qsys-interceptor.service qsys-server.service

sudo truncate -s 0 /etc/machine-id
sudo rm -f /var/lib/dbus/machine-id
sudo ln -sf /etc/machine-id /var/lib/dbus/machine-id

sudo rm -f /etc/ssh/ssh_host_*
sudo rm -f /var/lib/systemd/random-seed
sudo find /var/lib/dhcp -mindepth 1 -maxdepth 1 -type f -delete 2>/dev/null || true
sudo find /var/lib/NetworkManager -maxdepth 1 -type f -name '*lease*' -delete 2>/dev/null || true
sudo rm -f /var/lib/qsys-firstboot-identity.done
if [ -f /etc/systemd/system/qsys-firstboot-identity.service ]; then
  sudo systemctl enable qsys-firstboot-identity.service
fi

sudo journalctl --rotate
sudo journalctl --vacuum-time=1s
sudo find /tmp /var/tmp -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true

sync
sudo poweroff
```

## 3. Capture The Golden Image

Do the capture from another computer. Do not image the Pi while it is running
from the same SD card.

Remove the source SD card from the powered-off Pi and insert it into a Linux or
macOS computer.

### Linux

Find the SD card device:

```bash
lsblk -p -o NAME,SIZE,MODEL,MOUNTPOINTS
```

Use the whole-disk device, not a partition. For example, use `/dev/sdb`, not
`/dev/sdb1`. Choosing the wrong disk can overwrite your computer's data.

Unmount the mounted SD card partitions shown by `lsblk`. For example:

```bash
sudo umount /dev/sdX1 /dev/sdX2
```

Capture and compress the image:

```bash
sudo dd if=/dev/sdX bs=4M status=progress conv=fsync | gzip -1 > qsys-pi3-golden.img.gz
sync
```

Replace `/dev/sdX` with the actual SD card disk.

### macOS

Find the SD card device:

```bash
diskutil list
```

Unmount it:

```bash
diskutil unmountDisk /dev/diskN
```

Capture and compress the image:

```bash
sudo dd if=/dev/rdiskN bs=4m | gzip -1 > qsys-pi3-golden.img.gz
sync
diskutil eject /dev/diskN
```

Replace `diskN` and `rdiskN` with the actual SD card disk number.

### Windows

Use a disk imaging tool that can read an SD card into an `.img` file, such as
Win32 Disk Imager or USBImager. Select the source SD card, choose a destination
file such as `qsys-pi3-golden.img`, and use the tool's read/copy function.

## 4. Optional: Shrink The Image

An image made from a 32 GB card normally needs another 32 GB or larger card.
For easiest cloning, build the source Pi on the smallest SD card size you plan
to deploy.

If you need the image to fit smaller cards, shrink it on Linux with a Raspberry
Pi image shrinking tool such as PiShrink:

```bash
sudo pishrink.sh -z qsys-pi3-golden.img
```

Keep an untouched backup of the original image until the shrunken image has
been tested.

## 5. Burn The Image To A Fresh SD Card

Use a new SD card that is the same size or larger than the source card unless
you have shrunk the image.

### Raspberry Pi Imager

1. Open Raspberry Pi Imager.
2. Choose the Raspberry Pi 3 device.
3. Choose OS, then select `Use custom`.
4. Select `qsys-pi3-golden.img` or `qsys-pi3-golden.img.gz`.
5. Choose the fresh SD card.
6. Write the image.
7. Eject the card when verification finishes.

Avoid applying Raspberry Pi Imager customizations unless you intentionally want
to override settings from the golden image.

### Linux

Find the fresh SD card:

```bash
lsblk -p -o NAME,SIZE,MODEL,MOUNTPOINTS
```

Use the whole-disk device, not a partition. For example, use `/dev/sdb`, not
`/dev/sdb1`. Choosing the wrong disk can overwrite your computer's data.

Unmount the mounted SD card partitions shown by `lsblk`. For example:

```bash
sudo umount /dev/sdX1 /dev/sdX2
```

Write the compressed image:

```bash
gunzip -c qsys-pi3-golden.img.gz | sudo dd of=/dev/sdX bs=4M status=progress conv=fsync
sync
sudo eject /dev/sdX
```

Replace `/dev/sdX` with the actual fresh SD card disk.

### macOS

Find and unmount the fresh SD card:

```bash
diskutil list
diskutil unmountDisk /dev/diskN
```

Write the compressed image:

```bash
gunzip -c qsys-pi3-golden.img.gz | sudo dd of=/dev/rdiskN bs=4m
sync
diskutil eject /dev/diskN
```

Replace `diskN` and `rdiskN` with the actual fresh SD card disk number.

### Windows

Use Raspberry Pi Imager, balenaEtcher, Win32 Disk Imager, or USBImager. Select
the golden `.img` or `.img.gz`, select the fresh SD card, then write and eject
the card.

## 6. First Boot On The Cloned Pi

Insert the fresh SD card into the cloned Pi 3.

Before powering on:

- Plug Food, Drinks, and Chicken keypads into the labeled USB ports.
- Connect the display.
- Connect network if the image expects wired Ethernet, or make sure the saved
  Wi-Fi credentials are correct.
- If you installed the optional first-boot helper, mount the SD card boot
  partition and create a `qsys-hostname` file containing this Pi's hostname,
  such as `qsys-01`.

Power on the Pi and wait for it to finish booting. If you did not use a
`qsys-hostname` file, set a unique hostname:

```bash
sudo hostnamectl set-hostname qsys-01
sudo systemctl restart systemd-hostnamed
```

Regenerate SSH host keys if SSH is enabled and they were not regenerated
automatically:

```bash
sudo ssh-keygen -A
sudo systemctl restart ssh
```

If the clone uses the same keypad models in the same USB ports, the `.env` from
the golden image should already point at the right `/dev/input/by-path` entries.
Only refresh keypad paths if the ports or receivers changed, or if keypad input
does not work:

```bash
cd /home/pi/qsys
python3 scripts/update_keypad_env.py --order food,drinks,chicken
sudo systemctl restart qsys-interceptor.service
```

Verify the clone:

```bash
hostname
hostname -I
cat /etc/machine-id
ls -l /dev/input/by-path/
systemctl status qsys-server.service
systemctl status qsys-interceptor.service
```

Submit a test order:

```bash
curl -X POST http://127.0.0.1:8080/api/v1/queue \
  -H 'Content-Type: application/json' \
  -d '{"station":"food","number":"12"}'
```

## Troubleshooting

If two cloned Pis show the same hostname, set a unique hostname on each Pi:

```bash
sudo hostnamectl set-hostname qsys-02
```

If two cloned Pis appear to have the same machine identity, reset it on the
affected Pi and reboot:

```bash
sudo rm -f /etc/machine-id /var/lib/dbus/machine-id
sudo systemd-machine-id-setup
sudo ln -sf /etc/machine-id /var/lib/dbus/machine-id
sudo reboot
```

If keypad assignments are wrong, confirm the USB port layout:

```bash
ls -l /dev/input/by-path/
cd /home/pi/qsys
python3 scripts/update_keypad_env.py --order food,drinks,chicken
sudo systemctl restart qsys-interceptor.service
```

If the SD card does not boot, write the image again and confirm you selected the
whole disk device, not one partition.
