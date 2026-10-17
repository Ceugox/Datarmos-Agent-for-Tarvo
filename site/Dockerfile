# Site estático da Datarmos. O contexto de build é uma pasta montada por deploy.sh (site/ + saida/ em relatorio/).
FROM caddy:2.8.4-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY . /srv
RUN rm -f /srv/Dockerfile /srv/Caddyfile /srv/build_data.py /srv/deploy.sh /srv/railway.json
