# iablocklabs/celery.py
import os
from celery import Celery

# Configuration de Django pour Celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iablocklabs.settings')

app = Celery('iablocklabs')

# Configuration à partir des settings Django
app.config_from_object('django.conf:settings', namespace='CELERY')

# Découverte automatique des tâches
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')