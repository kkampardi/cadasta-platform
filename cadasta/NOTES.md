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
