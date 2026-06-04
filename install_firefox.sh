#!/bin/bash
cd /tmp
wget -q "https://download.mozilla.org/?product=firefox-latest-ssl&os=linux64&lang=en-US" -O firefox.tar.bz2
tar xjf firefox.tar.bz2 -C /opt/
ln -sf /opt/firefox/firefox /usr/bin/firefox
echo "FIREFOX OK"
