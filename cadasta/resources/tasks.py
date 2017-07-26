from tasks.celery import app


@app.task(name='export.export')
def export(org_slug, project_slug, api_key, type):
    pass


@app.task(name='msg.email')
def email(task, to_address):
    pass


@app.task(name='msg.email_err')
def email_err(task, to_address):
    pass
