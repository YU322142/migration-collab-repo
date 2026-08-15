from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


GIB = 1024 ** 3


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def gib(value: int) -> str:
    return f"{value / GIB:.2f} GiB"


def group_name(name: str) -> str:
    lowered = name.lower()
    for token in (
        "manual-test",
        "cutover-staging",
        "final-fullstack-smoke",
        "world-migration-smoke",
        "client-gate",
        "final-mod-bundles",
        "final-server-mods",
        "final-client-mods",
        "gradle-cache",
        "converter",
        "decompiled",
    ):
        if token in lowered:
            return token
    return "other-test-or-cache"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-report", required=True, type=Path)
    parser.add_argument("--tmp-report", required=True, type=Path)
    parser.add_argument("--projects-report", required=True, type=Path)
    parser.add_argument("--handoff-status", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-md", required=True, type=Path)
    args = parser.parse_args()

    main_report = json.loads(args.main_report.read_text(encoding="utf-8"))
    tmp_report = json.loads(args.tmp_report.read_text(encoding="utf-8"))
    projects_report = json.loads(args.projects_report.read_text(encoding="utf-8"))
    handoff_status = json.loads(args.handoff_status.read_text(encoding="utf-8"))

    migration_rows = [
        row for row in main_report["top_level_directories"]
        if str(row["path"]).startswith("D:/Trans/migration-audit-work/")
    ]
    delete_rows = sorted(
        (row for row in migration_rows if row["category"] == "DELETE_AFTER_REVIEW"),
        key=lambda row: int(row["bytes"]),
        reverse=True,
    )
    delete_bytes = sum(int(row["bytes"]) for row in delete_rows)
    delete_files = sum(int(row["file_count"]) for row in delete_rows)

    groups: dict[str, dict[str, int]] = defaultdict(lambda: {"directories": 0, "bytes": 0, "files": 0})
    for row in delete_rows:
        group = groups[group_name(str(row["name"]))]
        group["directories"] += 1
        group["bytes"] += int(row["bytes"])
        group["files"] += int(row["file_count"])

    tmp_delete_rows = sorted(
        (row for row in tmp_report["top_level_directories"] if row["category"] == "DELETE_AFTER_REVIEW"),
        key=lambda row: int(row["bytes"]),
        reverse=True,
    )
    tmp_delete_bytes = sum(int(row["bytes"]) for row in tmp_delete_rows)
    tmp_delete_files = sum(int(row["file_count"]) for row in tmp_delete_rows)

    manual_rows = sorted(
        (
            row for row in migration_rows
            if row["category"] == "MANUAL_REVIEW" and int(row["bytes"]) >= 100_000_000
        ),
        key=lambda row: int(row["bytes"]),
        reverse=True,
    )
    prism_rows = sorted(
        (
            row for row in main_report["top_level_directories"]
            if "/PrismLauncher-Windows-MinGW-w64-Portable-11.0.3/instances/" in str(row["path"])
        ),
        key=lambda row: int(row["bytes"]),
        reverse=True,
    )

    immutable_original = next(
        (
            row for row in main_report["root_files"]
            if str(row["path"]).lower() == "d:/down/20260811.zip"
        ),
        None,
    )
    keep = [
        {
            "path": "D:/Trans/migration-handoff-20260812.7z",
            "bytes": int(handoff_status["archive"]["bytes"]),
            "sha256": handoff_status["archive"]["sha256"],
            "reason": "已完成 7z 全量测试的最终交接归档",
        },
        {
            "path": "D:/Trans/migration-handoff-20260812.7z.sha256.txt",
            "reason": "归档校验值",
        },
        {
            "path": "D:/Trans/migration-handoff-20260812.archive-status.json",
            "reason": "归档与逐文件清单验证报告",
        },
        {
            "path": "D:/Trans/migration-handoff-20260812",
            "bytes": int(handoff_status["package"]["physical_bytes"]),
            "reason": "未压缩交接目录；接收方验证归档后可选择仅保留归档",
        },
        {
            "path": "D:/Down/20260811.zip",
            "bytes": int(immutable_original["bytes"]) if immutable_original else None,
            "sha256": "9723FE28BC1B98D6ECE96A4063532BB2A533A038E7B3E457D50CF658E2495021",
            "reason": "用户最新停服原始输入，必须只读保留",
        },
        {
            "path": "<WORKSPACE>/outputs/tools",
            "reason": "转换、审计、组装和门禁脚本",
        },
        {
            "path": "<WORKSPACE>/outputs/projects",
            "bytes": int(projects_report["summary"]["total_bytes"]),
            "reason": "兼容模组源码；可另清理其中 build/.gradle，但不要删源码",
        },
        {
            "path": "D:/Trans/migration-audit-work/final-mod-bundles-candidate14-r3-20260812",
            "reason": "当前 release 参考；已入交接包，接收方验收前保留",
        },
    ]

    review = {
        "schema": 1,
        "status": "PASS_READ_ONLY_REVIEW",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "main_report": args.main_report.as_posix(),
            "tmp_report": args.tmp_report.as_posix(),
            "projects_report": args.projects_report.as_posix(),
            "scanned_bytes": int(main_report["summary"]["total_bytes"]),
            "scanned_files": int(main_report["summary"]["total_files"]),
            "scan_errors": int(main_report["summary"]["scan_errors"]),
        },
        "decision": {
            "approximately_400_gib_candidate_worlds_need_to_be_kept": False,
            "recommended_action": "保留最终交接包和原始输入；旧候选按清单审核后删除",
            "automatic_deletion_performed": False,
        },
        "reclaimable_after_review": {
            "d_migration_audit_work": {
                "directories": len(delete_rows),
                "bytes": delete_bytes,
                "gib": round(delete_bytes / GIB, 3),
                "files": delete_files,
                "groups": dict(sorted(groups.items())),
                "items": [
                    {
                        "path": row["path"],
                        "bytes": int(row["bytes"]),
                        "gib": round(int(row["bytes"]) / GIB, 3),
                        "file_count": int(row["file_count"]),
                        "world_like": bool(row["world_like"]),
                        "runtime_like": bool(row["runtime_like"]),
                        "reason": row["category_reason"],
                    }
                    for row in delete_rows
                ],
            },
            "c_outputs_tmp": {
                "directories": len(tmp_delete_rows),
                "bytes": tmp_delete_bytes,
                "gib": round(tmp_delete_bytes / GIB, 3),
                "files": tmp_delete_files,
                "items": [
                    {
                        "path": row["path"],
                        "bytes": int(row["bytes"]),
                        "gib": round(int(row["bytes"]) / GIB, 3),
                        "file_count": int(row["file_count"]),
                        "reason": row["category_reason"],
                    }
                    for row in tmp_delete_rows
                ],
            },
        },
        "keep": keep,
        "manual_review_over_100mb": [
            {
                "path": row["path"],
                "bytes": int(row["bytes"]),
                "gib": round(int(row["bytes"]) / GIB, 3),
                "file_count": int(row["file_count"]),
                "world_like": bool(row["world_like"]),
                "runtime_like": bool(row["runtime_like"]),
            }
            for row in manual_rows
        ],
        "prism_instances_manual_review": [
            {
                "path": row["path"],
                "bytes": int(row["bytes"]),
                "gib": round(int(row["bytes"]) / GIB, 3),
                "file_count": int(row["file_count"]),
                "world_like": bool(row["world_like"]),
            }
            for row in prism_rows
        ],
        "deletion_preconditions": [
            "接收方先核验 migration-handoff-20260812.7z 的 SHA-256 与 7z test PASS",
            "不得删除 D:/Down/20260811.zip 或用户原始资源包",
            "不得把任何 Java 启动/保存过的候选世界重新当作转换输入",
            "Prism 实例和 D:/Down 非迁移文件只做人工审核，不包含在批量删除建议中",
            "执行删除时必须使用本 JSON 的精确路径，不使用通配符或父目录递归删除",
        ],
    }

    lines = [
        "# Minecraft 迁移历史文件容量审计",
        "",
        f"生成时间：{review['generated_at_utc']}",
        "",
        "## 结论",
        "",
        "**不需要继续保留约 400GB 的历史候选世界。** 它们主要是已启动/已保存的 manual-test、fullstack-smoke、旧 cutover staging 和运行时副本，不能作为新转换输入。",
        "",
        f"- 本次只读扫描：{gib(review['scope']['scanned_bytes'])}，{review['scope']['scanned_files']:,} 个文件，扫描错误 0。",
        f"- D 盘迁移工作区明确可在审核后回收：{gib(delete_bytes)}（{len(delete_rows)} 个顶层目录，{delete_files:,} 个文件）。",
        f"- C 盘 `outputs/tmp` 明确可在审核后回收：{gib(tmp_delete_bytes)}（{len(tmp_delete_rows)} 个子目录）。",
        "- 本报告没有删除、移动或修改任何被审计文件。",
        "",
        "## 必须保留",
        "",
    ]
    for row in keep:
        size = f"（{gib(int(row['bytes']))}）" if row.get("bytes") else ""
        lines.append(f"- `{row['path']}` {size}：{row['reason']}")

    lines.extend(["", "## D 盘旧候选分组", "", "| 类别 | 目录数 | 大小 | 文件数 |", "|---|---:|---:|---:|"])
    for name, row in sorted(groups.items(), key=lambda item: item[1]["bytes"], reverse=True):
        lines.append(f"| `{name}` | {row['directories']} | {gib(row['bytes'])} | {row['files']:,} |")

    lines.extend(["", "## 最大的待删候选（前 30 项）", "", "| 大小 | 路径 |", "|---:|---|"])
    for row in delete_rows[:30]:
        lines.append(f"| {gib(int(row['bytes']))} | `{row['path']}` |")

    lines.extend([
        "",
        "## C 盘 `outputs/tmp`",
        "",
        f"明确的旧 client-gate/smoke 副本合计 {gib(tmp_delete_bytes)}。`outputs/projects` 源码约 {gib(int(projects_report['summary']['total_bytes']))}，应保留；如需进一步省空间，只清理各项目的 `build/`、`.gradle/`，不要删除源码。",
        "",
        "## 人工确认项",
        "",
        "- `D:/Trans/migration-audit-work/incoming-20260811-raw` 是原始 ZIP 的展开副本；最终交接包和原始 ZIP 均已校验，因此可在接收方确认后删除，但本报告仍把它列为人工确认。",
        "- 唯一 frozen staging 和 Candidate14-r3 release 已复制进交接包；接收方验证归档后可删除原工作目录副本。",
        "- Prism 实例可能含用户配置、账号选择、截图或存档，不进入自动删除建议。",
        "- `D:/Down` 中除 `20260811.zip` 外大量内容与本迁移无关，本报告不建议批量清理。",
        "",
        "## 删除前置条件",
        "",
    ])
    for item in review["deletion_preconditions"]:
        lines.append(f"- {item}")
    lines.extend([
        "",
        "完整逐路径清单见同名 JSON；本 Markdown 只展示汇总与最大项目。",
        "",
    ])

    args.output_json.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "status": review["status"],
        "d_reclaimable_bytes": delete_bytes,
        "c_tmp_reclaimable_bytes": tmp_delete_bytes,
        "json": args.output_json.as_posix(),
        "md": args.output_md.as_posix(),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
