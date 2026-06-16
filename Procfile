web: python manage.py migrate && python manage.py collectstatic --noinput && gunicorn Wildlife_Tracking_System.wsgi:application --bind 0.0.0.0:$PORT
