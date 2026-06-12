import csv
from pathlib import Path

path = Path('role_guesser/data/roles.csv')
rows = list(csv.DictReader(path.open('r', encoding='utf-8-sig', newline='')))
filtered = [row for row in rows if (row.get('name') or '').strip() != 'NOS_MetaRole']

with path.open('w', encoding='utf-8', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(filtered)

print('removed', len(rows) - len(filtered), 'rows')
print('remaining', len(filtered), 'rows')
