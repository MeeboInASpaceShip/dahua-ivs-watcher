# dahua-ivs-watcher
## Python Dahua IVS event watcher

Built on https://i.botox.bz/watch.py that was extended by @johnnyletrois to publish MQTT messages: 
https://github.com/johnnyletrois/dahua-watch.

This version was built to trigger Synology Surveillance Station to start a External Event recording when a configured 
IVS event is received, instead of publishing with MQTT.

It's a bit of a hack and I have only tried it with a single camera. Please pull, clone and extend. I would love to hear 
about extensions and updates!

## Installation
The script has a few comments in the code that hopefully gets you started. Surveillance Station documentation can hopefully
help you further.

## Usage
I'm running the script on a RPi running Debian 10.0 and systemd, so I run it as a system service. 

### /etc/systemd/system/dahua-ivs.service
```
[Unit]
Description=Dahua IVS event watcher
After=syslog.target

[Service]
Type=simple
User=nobody
Group=nogroup
ExecStart=/usr/local/bin/dahua-ivs.py
Restart=always
StandardOutput=syslog
StandardError=syslog

[Install]
WantedBy=multi-user.target
