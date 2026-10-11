#!/bin/bash
# Put the Link relay on a web server that runs nginx and PHP-FPM. Run as root, from this folder:
#
#   ./install.sh /etc/nginx/sites-available/visualised.io
#
# It copies link.php, pair.php and pass.php to /var/www/shared/vml-link, makes /var/lib/vml-link for its small database, and adds
#   location = /link/ { ... }
# to the site, in front of each "location /downloads/" already there. The site's file is copied first, nginx
# is asked whether it is happy, and if it isn't the copy is put back. Then the relay is tried.
set -eu
[ "$(id -u)" -eq 0 ] || { echo "run this as root (sudo)"; exit 1; }
site=${1:-}
[ -f "$site" ] || { sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }
here=$(cd "$(dirname "$0")" && pwd)
sock=$(ls /run/php/php*-fpm.sock 2>/dev/null | sort -V | tail -1)
[ -n "$sock" ] || { echo "PHP-FPM isn't running here (no /run/php/php*-fpm.sock)"; exit 1; }
php -m 2>/dev/null | grep -qi sodium || { echo "PHP has no sodium, which checks licences (apt install php-sodium, or it comes with php 7.2 and later)"; exit 1; }
php -m 2>/dev/null | grep -qi pdo_sqlite || { echo "PHP has no SQLite (apt install php-sqlite3)"; exit 1; }

install -d -m 755 /var/www/shared/vml-link
install -m 644 "$here/link.php" /var/www/shared/vml-link/link.php
install -m 644 "$here/pair.php" /var/www/shared/vml-link/pair.php
install -m 644 "$here/pass.php" /var/www/shared/vml-link/pass.php
install -d -m 700 -o www-data -g www-data /var/lib/vml-link

if grep -q "location = /link/" "$site"; then
    echo "the site already has the relay's location: only the program was updated"
else
    grep -q "location /downloads/" "$site" || { echo "no 'location /downloads/' in $site to put it in front of: add the block by hand (it is in this script)"; exit 1; }
    keep="$site.before-link.$(date +%Y%m%d-%H%M%S)"
    cp -p "$site" "$keep"
    block="    location = /link/ {\n        include fastcgi_params;\n        fastcgi_param SCRIPT_FILENAME /var/www/shared/vml-link/link.php;\n        fastcgi_param LINK_DB /var/lib/vml-link/link.db;\n        fastcgi_pass unix:$sock;\n        client_max_body_size 64k;\n    }\n\n"
    sed -i "s|^\([[:space:]]*\)location /downloads/|$block\1location /downloads/|" "$site"
    if nginx -t 2>/dev/null; then
        systemctl reload nginx
        echo "added to $site (the file as it was: $keep)"
    else
        cp -p "$keep" "$site"
        echo "nginx did not like the change, so the site's file was put back as it was:"; nginx -t 2>&1 | tail -3
        exit 1
    fi
fi
echo "PHP-FPM socket: $sock"
