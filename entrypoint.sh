#! /bin/bash
set -e

/bin/bash -c "python3 /home/$user/src/backend/manage.py makemigrations"
/bin/bash -c "python3 /home/$user/src/backend/manage.py migrate"
/bin/bash -c "python3 /home/$user/src/backend/manage.py create_superuser"
/bin/bash -c "python3 /home/$user/src/backend/manage.py collectstatic --noinput"

supervisord -n -c /etc/supervisord.conf
