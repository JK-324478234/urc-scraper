from pathlib import Path
import json

class RugbyParser:

    def __init__(self, html_file):
        self.html = Path(html_file).read_text(encoding="utf-8")

    def extract_records(self):

        records = []

        i = 0

        while True:

            start = self.html.find(r'{\"rank\"', i)

            if start == -1:
                break

            depth = 0
            end = start

            while end < len(self.html):

                if self.html[end] == "{":
                    depth += 1

                elif self.html[end] == "}":
                    depth -= 1

                    if depth == 0:
                        break

                end += 1

            obj = self.html[start:end + 1]

            try:
                obj = obj.replace(r'\"', '"')
                records.append(json.loads(obj))
            except:
                pass

            i = end + 1

        return records


if __name__ == "__main__":

    parser = RugbyParser("world-rugby.html")
    records = parser.extract_records()

    print(f"Loaded {len(records)} records\n")

    # Count record types
    types = {}

    for record in records:

        keys = tuple(sorted(record.keys()))

        types[keys] = types.get(keys, 0) + 1

    print(f"Found {len(types)} different record structures:\n")

    for i, (keys, count) in enumerate(sorted(types.items(), key=lambda x: x[1], reverse=True), 1):

        print(f"Type {i} - {count} records")
        print(keys)
        print("-" * 80)