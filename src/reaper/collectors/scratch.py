import datetime
from azure.mgmt.costmanagement.models import QueryTimePeriod
end = datetime.datetime.now(datetime.timezone.utc)
start = end - datetime.timedelta(days=30)
q = QueryTimePeriod(from_property=start, to=end)
print(q.serialize())
