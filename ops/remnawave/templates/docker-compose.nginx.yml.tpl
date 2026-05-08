x-common: &common
  restart: always

services:
  remnawave-nginx:
    image: nginx:1.28
    container_name: remnawave-nginx
    hostname: remnawave-nginx
    <<: [*common]
    network_mode: host
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - /etc/letsencrypt/live/__CERT_DOMAIN__/fullchain.pem:/etc/nginx/ssl/nodedomain/fullchain.pem:ro
      - /etc/letsencrypt/live/__CERT_DOMAIN__/privkey.pem:/etc/nginx/ssl/nodedomain/privkey.pem:ro
      - /dev/shm:/dev/shm:rw
      - /var/www/html:/var/www/html:ro
    command: sh -c 'rm -f /dev/shm/nginx.sock && exec nginx -g "daemon off;"'

  remnanode:
    image: remnawave/node:latest
    container_name: remnanode
    hostname: remnanode
    <<: [*common]
    network_mode: host
    cap_add:
      - NET_ADMIN
    environment:
      - NODE_PORT=__NODE_PORT__
      - SECRET_KEY=__NODE_SECRET_KEY__
    volumes:
      - /etc/letsencrypt/live/__CERT_DOMAIN__/fullchain.pem:/etc/nginx/ssl/nodedomain/fullchain.pem:ro
      - /etc/letsencrypt/live/__CERT_DOMAIN__/privkey.pem:/etc/nginx/ssl/nodedomain/privkey.pem:ro
      - /dev/shm:/dev/shm:rw
