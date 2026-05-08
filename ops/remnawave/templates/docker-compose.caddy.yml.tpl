x-common: &common
  restart: always

services:
  remnawave-caddy:
    image: caddy:2
    container_name: remnawave-caddy
    hostname: remnawave-caddy
    <<: [*common]
    network_mode: host
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
      - /var/www/html:/var/www/html:ro

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
      - /dev/shm:/dev/shm:rw

volumes:
  caddy_data:
  caddy_config:
