FROM postgres:16-alpine
RUN apk add --no-cache bash gnupg rsync openssh-client tzdata
COPY backup.sh restore.sh restore-test.sh entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/*.sh
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
