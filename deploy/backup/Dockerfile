# Daily encrypted pg_dump of the production database to object storage (see backup.sh).
# pg_dump 17 reads Supabase's Postgres 15 and 17; backup.sh refuses a newer server.
FROM postgres:17-alpine

RUN apk add --no-cache age rclone bash

COPY backup.sh restore-inside.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/restore-inside.sh

USER postgres
ENTRYPOINT ["/usr/local/bin/backup.sh"]
