#!/bin/bash
service nginx start
Xvfb :0 -screen 0 1920x1080x24 &
sleep 3
x11vnc -display :0 -forever -shared -nopw &
sleep 2
websockify --web=/usr/share/novnc/ 6080 localhost:5900 &
sleep 1
exec startxfce4
