from __future__ import annotations

import argparse
from collections import Counter

from nbt import nbt


def collect_items(value, ids, full):
    if isinstance(value, nbt.TAG_Compound):
        item_id = value.get("id")
        count = value.get("count", value.get("Count"))
        if isinstance(item_id, nbt.TAG_String) and isinstance(count, (nbt.TAG_Byte, nbt.TAG_Short, nbt.TAG_Int, nbt.TAG_Long)) and int(count.value) > 0:
            ids[(item_id.value, int(count.value))] += 1
            full[(item_id.value, int(count.value), canonical(value))] += 1
        for child in value.values():
            collect_items(child, ids, full)
    elif isinstance(value, nbt.TAG_List):
        for child in value:
            collect_items(child, ids, full)


def find_item_paths(value, path, wanted, result):
    if isinstance(value, nbt.TAG_Compound):
        item_id = value.get("id")
        count = value.get("count", value.get("Count"))
        if isinstance(item_id, nbt.TAG_String) and item_id.value == wanted and isinstance(count, (nbt.TAG_Byte, nbt.TAG_Short, nbt.TAG_Int, nbt.TAG_Long)) and int(count.value) > 0:
            result.append(path)
        for key, child in value.items():
            find_item_paths(child, f"{path}.{key}" if path else key, wanted, result)
    elif isinstance(value, nbt.TAG_List):
        for index, child in enumerate(value):
            find_item_paths(child, f"{path}[{index}]", wanted, result)


def canonical(value):
    if isinstance(value, nbt.TAG_Compound):
        return ("compound", tuple(sorted((key, canonical(child)) for key, child in value.items())))
    if isinstance(value, nbt.TAG_List):
        return ("list", tuple(canonical(child) for child in value))
    if isinstance(value, (nbt.TAG_Byte_Array, nbt.TAG_Int_Array, nbt.TAG_Long_Array)):
        return (type(value).__name__, tuple(value.value))
    return (type(value).__name__, scalar(value))


def scalar(tag):
    if isinstance(tag, (nbt.TAG_Byte_Array, nbt.TAG_Int_Array, nbt.TAG_Long_Array)):
        return tuple(tag.value)
    return getattr(tag, "value", tag)


def compare(left, right, path, differences, limit):
    if len(differences) >= limit:
        return
    if type(left) is not type(right):
        differences.append((path, type(left).__name__, type(right).__name__))
        return
    if isinstance(left, nbt.TAG_Compound):
        for key in sorted(set(left.keys()) | set(right.keys())):
            child_path = f"{path}.{key}" if path else key
            if key not in left:
                differences.append((child_path, "<missing>", type(right[key]).__name__))
            elif key not in right:
                differences.append((child_path, type(left[key]).__name__, "<missing>"))
            else:
                compare(left[key], right[key], child_path, differences, limit)
            if len(differences) >= limit:
                return
        return
    if isinstance(left, nbt.TAG_List):
        if len(left) != len(right):
            differences.append((path + ".length", len(left), len(right)))
        for index, (a, b) in enumerate(zip(left, right)):
            compare(a, b, f"{path}[{index}]", differences, limit)
            if len(differences) >= limit:
                return
        return
    a, b = scalar(left), scalar(right)
    if a != b:
        differences.append((path, a, b))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("left")
    parser.add_argument("right")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--items", action="store_true")
    parser.add_argument("--find-item")
    args = parser.parse_args()
    left = nbt.NBTFile(filename=args.left)
    right = nbt.NBTFile(filename=args.right)
    if args.find_item:
        for label, root in (("LEFT", left), ("RIGHT", right)):
            paths = []
            find_item_paths(root, "", args.find_item, paths)
            print(label, len(paths))
            print("\n".join(paths))
        return
    if args.items:
        left_ids, left_full = Counter(), Counter()
        right_ids, right_full = Counter(), Counter()
        collect_items(left, left_ids, left_full)
        collect_items(right, right_ids, right_full)
        print("ITEM_ID_COUNT_DELTAS")
        for key in sorted(set(left_ids) | set(right_ids)):
            if left_ids[key] != right_ids[key]:
                print(f"{key}\t{left_ids[key]}\t{right_ids[key]}")
        print("ITEM_FULL_STACK_DELTAS")
        shown = 0
        for key in sorted(set(left_full) | set(right_full), key=repr):
            if left_full[key] == right_full[key]:
                continue
            print(f"{key!r}\t{left_full[key]}\t{right_full[key]}")
            shown += 1
            if shown >= args.limit:
                break
        print(f"ITEM_TOTALS={sum(left_ids.values())},{sum(right_ids.values())}")
        return
    differences = []
    compare(left, right, "", differences, args.limit)
    for path, a, b in differences:
        print(f"{path}\t{a!r}\t{b!r}")
    print(f"DIFFERENCES_SHOWN={len(differences)} LIMIT={args.limit}")


if __name__ == "__main__":
    main()
