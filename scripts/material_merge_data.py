"""Prepare, apply and verify material identity migration while all writers are stopped."""

import argparse
import base64
import copy
import hashlib
import json
import os
import re
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

OLD_HEAD = "9e4b6c8d201a"
NEW_HEAD = "a51e9c7d204b"
PROJECT_FIELDS = {
    "goal", "current_level", "deadline", "daily_minutes", "weekly_days", "expected_outcome",
}
JSON_FIELDS = (
    ("plan_versions", "content"), ("replan_proposals", "proposed_content"),
    ("replan_proposals", "diff"), ("audit_events", "payload"),
)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def snapshot(engine):
    result = {}
    with engine.connect() as db:
        quote = db.dialect.identifier_preparer.quote
        for name in sorted(inspect(db).get_table_names()):
            if name == "alembic_version":
                continue
            require("id" in {c["name"] for c in inspect(db).get_columns(name)},
                    "Unrecognized table without id: " + name)
            result[name] = list(db.execute(text(
                f"SELECT row_to_json(t) FROM (SELECT * FROM {quote(name)} ORDER BY id) t"
            )).scalars())
    return result


def head(engine):
    with engine.connect() as db:
        return db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def translated(value, mapping):
    if isinstance(value, list):
        return [translated(item, mapping) for item in value]
    if not isinstance(value, dict):
        return value
    out = {}
    for key, item in value.items():
        if key == "material_version_id":
            require(type(item) is int and item in mapping and "material_id" not in value,
                    "Unknown or ambiguous historical material reference")
            out["material_id"] = mapping[item]
        else:
            require("material_version" not in key, "Unrecognized material reference key")
            out[key] = translated(item, mapping)
    return out


def expected_rows(before):
    after = copy.deepcopy(before)
    versions = after.pop("material_versions")
    mapping = {v["id"]: v["material_id"] for v in versions}
    by_material = {v["material_id"]: v for v in versions}
    require(len(by_material) == len(versions), "Multiple file records")
    require(set(by_material) == {m["id"] for m in after["materials"]}, "Missing file record")
    for material in after["materials"]:
        require(material.pop("enabled") is True and material["deletion_started_at"] is None,
                "Disabled material or unfinished cleanup")
        version = by_material[material["id"]]
        require(version["version_number"] == 1, "Non-default material version")
        require(version["parse_status"] not in ("QUEUED", "PARSING"), "Active parsing")
        material.update({k: v for k, v in version.items()
                         if k not in ("id", "material_id", "version_number")})
    for project in after["learning_projects"]:
        for name in PROJECT_FIELDS:
            project.pop(name)
    for source in after["knowledge_node_sources"]:
        source["material_id"] = mapping[source.pop("material_version_id")]
    for table_name, column in JSON_FIELDS:
        for row in after[table_name]:
            row[column] = translated(row[column], mapping)
    return after


def safe_path(root, relative):
    path = Path(relative)
    require(not path.is_absolute() and bool(path.parts) and ".." not in path.parts,
            "Unsafe relative path")
    current = root
    for part in path.parts:
        current = current / part
        require(not current.is_symlink(), "Symlink is not a migration target")
    require(current.resolve().is_relative_to(root), "Path escapes material root")
    return current


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(data):
    return base64.b64encode(data).decode("ascii")


def prepare(engine, root, manifest):
    require(head(engine) == OLD_HEAD, "Prepare only from the original migration head")
    before = snapshot(engine)
    expected_rows(before)  # All database preconditions and JSON references checked first.
    materials = {m["id"]: m for m in before["materials"]}
    files = []
    for version in before["material_versions"]:
        material_id = version["material_id"]
        owner = materials[material_id]["user_id"]
        original = version["storage_object_key"]
        require(re.fullmatch(rf"{owner}/[0-9a-f]{{32}}\.(md|markdown)", original),
                "Unsupported original file path")
        content = safe_path(root, original).read_bytes()
        require(digest(content) == version["content_hash"], "Original file hash mismatch")
        files.append({"path": original, "hash": digest(content)})
        parsed = version["parsed_content_location"]
        metadata = version["source_metadata"]
        require(version["parse_status"] != "READY" or (parsed and metadata),
                "READY result is incomplete")
        allowed = set()
        if parsed is not None:
            require(re.fullmatch(rf"parsed/{material_id}/{version['id']}\.md", parsed),
                    "Unexpected parsed file path")
            sources = str(Path(parsed).with_suffix(".sources.json"))
            require(isinstance(metadata, dict) and metadata.get("sources_path") == sources,
                    "Source metadata path mismatch")
            parsed_bytes = safe_path(root, parsed).read_bytes()
            files.append({"path": parsed, "hash": digest(parsed_bytes)})
            source_bytes = safe_path(root, sources).read_bytes()
            source_map = json.loads(source_bytes)
            require(isinstance(source_map, dict)
                    and source_map.get("material_version_id") == version["id"]
                    and "material_id" not in source_map, "Source map identity mismatch")
            migrated = dict(source_map)
            migrated["material_id"] = material_id
            del migrated["material_version_id"]
            after_bytes = json.dumps(migrated, ensure_ascii=False, indent=2).encode("utf-8")
            files.append({"path": sources, "before": encode(source_bytes), "after": encode(after_bytes)})
            allowed = {Path(parsed).name, Path(sources).name}
        else:
            require(metadata is None, "Metadata without parsed file")
        directory = safe_path(root, f"parsed/{material_id}/.check").parent
        if directory.exists():
            require({p.name for p in directory.iterdir()} == allowed,
                    "Unknown files in material parse directory; review before migration")
    data = {"format": 1, "before": before, "files": files}
    # Manifest contains user data; keep it in the protected backup directory.
    with manifest.open("x", encoding="utf-8") as output:
        json.dump(data, output, ensure_ascii=False)
        output.flush()
        os.fsync(output.fileno())
    print("MATERIAL_MERGE_PREPARED", len(materials), "materials")


def apply_or_verify(engine, root, manifest, apply):
    require(head(engine) == NEW_HEAD, "Requires merged database head")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    require(data["format"] == 1, "Unknown manifest format")
    require(snapshot(engine) == expected_rows(data["before"]), "Database rows differ from expected mapping")
    writes = []
    for item in data["files"]:
        path = safe_path(root, item["path"])
        current = path.read_bytes()
        if "hash" in item:
            require(digest(current) == item["hash"], "Original or parsed text changed")
        else:
            before = base64.b64decode(item["before"])
            after = base64.b64decode(item["after"])
            require(current in (before, after) if apply else current == after,
                    "Unexpected source file contents")
            temporary = path.with_name("." + path.name + ".material-merge.tmp")
            require(not temporary.is_symlink(), "Linked migration temporary file")
            if apply and (current != after or temporary.exists()):
                writes.append((path, after))
    # Validate every file first; atomic replacement is per file, not a distributed transaction.
    # On interruption keep writers stopped and rerun apply with the SAME manifest.
    for path, content in writes:
        temporary = path.with_name("." + path.name + ".material-merge.tmp")
        try:
            with temporary.open("wb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    if apply:
        apply_or_verify(engine, root, manifest, False)
    else:
        print("MATERIAL_MERGE_VERIFIED: database rows, source identities and file hashes")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "apply", "verify"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("data/materials"))
    args = parser.parse_args()
    engine = create_engine(os.environ["DATABASE_URL"])
    require(engine.dialect.name == "postgresql", "PostgreSQL required")
    root = args.root.resolve()
    require(root.is_dir() and not args.root.is_symlink(), "Material root missing or linked")
    try:
        if args.action == "prepare":
            prepare(engine, root, args.manifest)
        else:
            apply_or_verify(engine, root, args.manifest, args.action == "apply")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()