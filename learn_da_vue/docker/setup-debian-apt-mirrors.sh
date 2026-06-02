#!/bin/sh
set -e

APT_MIRROR="${APT_MIRROR:-mirrors.tuna.tsinghua.edu.cn}"

if [ -f /etc/apt/sources.list.d/debian.sources ]; then
    sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources
    sed -i "s|security.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources
elif [ -f /etc/apt/sources.list ]; then
    sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list
    sed -i "s|security.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list
fi
