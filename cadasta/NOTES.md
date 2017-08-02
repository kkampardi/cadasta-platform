# Export Needs

## Shp Export:


### `relationships.csv`

Dump of `project.tenure_relationships.all()`

#### Fields

* `id`
* `party_id`
* `spatial_unit_id`
* `tenure_type`

_TODO: How do we handle the `get_schem_attrs(content_type)` on the worker?_

#### API Equivalent

`/api/v1/organizations/cadasta/projects/london-2/relationships/tenure/`

_NOTE: This doesn't seem to work..._


### `parties.csv`

Dump of `project.parties.all()`

#### Fields

* `id`
* `name`
* `type`

#### API Equivalent

`/api/v1/organizations/cadasta/projects/london-2/parties/`


### `locations.csv`

#### API Equivalent

`/api/v1/organizations/cadasta/projects/london-2/spatial/`

### ShapeFiles


### `shp_readme.txt`


### `README.txt`

## Auth

```python
from rest_framework_tmp_scoped_token import TemporaryApiToken
u = User.objets.first()
token = TemporaryApiToken(u, {'GET': ['/api/v1/organizations/cadasta/projects/london-2']}).generate_signed_token()

import requests
sesh = requests.session()
sesh.headers['Authorization'] = 'TmpToken %s' % token
url = 'http://localhost:8000/api/v1/organizations/cadasta/projects/london-2/parties/'
sesh.get(url).json()
```


## DB Setup

```sql
GRANT SELECT ON celery_taskmeta TO asyncworker ;
GRANT UPDATE ON celery_taskmeta TO asyncworker ;
GRANT INSERT ON celery_taskmeta TO asyncworker ;
GRANT USAGE ON task_id_sequence TO asyncworker ;
```

## Design Notes

### Scheduling Followup Actions

Imagine a workflow where we have a Task Producer that wants to schedule an operation and then specify a success-handler (e.g. `chain(BigSystemSummary.s(), EmailResult.s())()` or `BigSystemSummary.apply_async(link=EmailSuccess.s(), link_error=EmailFailure.s())`).

However, consider that the `BigSystemSummary` task is written encompassing [granularity](http://celery.readthedocs.io/en/latest/userguide/tasks.html#granularity):

```python
@app.task()
def BigSystemSummary():
    return chord(
        get_user_stats.s(),
        get_db_stats.s(),
        get_aws_stats.s()
    )(merge_and_store_data.s())
```

We obviously [don't want `BigSystemSummary` waiting synchronously for the results of its subtasks](http://celery.readthedocs.io/en/latest/userguide/tasks.html#avoid-launching-synchronous-subtasks). However, herein-lies the problem. `BigSystemSummary` will successfully complete quickly and run `EmailSuccess` before `merge_and_store_data` has had a chance to handle all the data.  We could write all of the subtask logic on the Task Producer, but I feel like this is a bit of anti-pattern as ideally we don't want the Task Producer to be concerned with _how_ `BigSystemSummary` works. Conversely, we could put the success/failure handlers into the `BigSystemSummary` task, however again we don't want to couple that logic and instead would rather have the Task Producer have the flexibility of dictating what to do as a followup.

To acheive this, followup actions should be passed as `celery.Signature` objects to the task as `on_success` and `on_failure` options.


### Running Workers

Workers should always be listening to their queue and the celery queue. The celery queue is used to process meta-tasks such as handling [chords](http://docs.celeryproject.org/en/latest/userguide/canvas.html#chords).

