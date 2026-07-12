from pathlib import Path
import json
import csv


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


parser = RugbyParser("world-rugby.html")
records = parser.extract_records()

merged = {}

for record in records:

    # PLAYER RECORD
    if "player" in record:

        key = ("Player", record.get("player"), record.get("team"))

        if key not in merged:
            merged[key] = {
                "Type": "Player",
                "Player": record.get("player"),
                "Team": record.get("team"),
                "Rank": record.get("rank")
            }

        values = record.get("values", {})

        for stat, value in values.items():
            merged[key][stat] = value

    # TEAM TABLE RECORD
    elif "team" in record and "played" in record:

        key = ("Team", "", record.get("team"))

        if key not in merged:
            merged[key] = {
                "Type": "Team",
                "Player": "",
                "Team": record.get("team"),
                "Rank": record.get("rank"),

                "Played": record.get("played"),
                "Won": record.get("won"),
                "Lost": record.get("lost"),
                "Drawn": record.get("drawn"),
                "Points Difference": record.get("pd"),
                "Bonus Points": record.get("bp"),
                "Competition Points": record.get("pts")
            }

    # TEAM STAT RECORD
    elif "name" in record:

        key = ("Team", "", record.get("name"))

        if key not in merged:
            merged[key] = {
                "Type": "Team",
                "Player": "",
                "Team": record.get("name"),
                "Rank": record.get("rank")
            }

        merged[key]["Value"] = record.get("value")

rows = list(merged.values())

fieldnames = sorted(set().union(*(row.keys() for row in rows)))

with open("rugby_stats.csv", "w", newline="", encoding="utf-8") as f:

    writer = csv.DictWriter(f, fieldnames=fieldnames)

    writer.writeheader()
    writer.writerows(rows)

print(f"Exported {len(rows)} records")