# Emulates the edge VM as it exists in production today. Not part of the task.
FROM openresty/openresty:1.27.1.2-alpine
RUN apk add --no-cache python3 openssl \
 && rm -f /etc/nginx/conf.d/default.conf \
 && mkdir -p /usr/local/openresty/nginx/conf/sites-enabled /etc/openresty/certs \
 && openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
      -subj "/CN=shoplite.local" \
      -keyout /etc/openresty/certs/tls.key -out /etc/openresty/certs/tls.crt
COPY nginx.conf /usr/local/openresty/nginx/conf/nginx.conf
COPY shop.conf /usr/local/openresty/nginx/conf/sites-enabled/shop.conf
RUN printf "allow 127.0.0.1;\nallow 172.16.0.0/12;\n" > /usr/local/openresty/nginx/conf/metrics-allow.conf
