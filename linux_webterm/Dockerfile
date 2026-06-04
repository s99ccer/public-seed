FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:0

RUN apt-get update && apt-get install -y \
    xfce4 \
    xfce4-goodies \
    x11vnc \
    novnc \
    websockify \
    xvfb \
    dbus-x11 \
    xorg \
    sudo \
    curl \
    wget \
    vim \
    nano \
    htop \
    net-tools \
    iputils-ping \
    git \
    python3 \
    python3-pip \
    tree \
    less \
    locales \
    nginx \
    openssl \
    && rm -rf /var/lib/apt/lists/*

RUN locale-gen en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

RUN useradd -m -s /bin/bash user && echo "user:user" | chpasswd && usermod -aG sudo user

RUN mkdir -p /etc/nginx/ssl && \
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/server.key \
    -out /etc/nginx/ssl/server.pem \
    -subj '/C=KR/ST=Seoul/L=Seoul/O=Docker/CN=localhost'

COPY nginx_https.conf /etc/nginx/sites-available/default
RUN rm -f /etc/nginx/sites-enabled/default && \
    ln -sf /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default

COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 443 6080

CMD ["/start.sh"]
