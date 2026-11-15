"""Command-line interface for the black-box English -> Chinese tool."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from .engine import TranslationEngine, VERSION
from .lexicon import Lexicon
from .mtran import MTranClient, MTranError, MTranUnavailable


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zhtrans",
        description="离线英译中：本地纠错 + MTranServer 翻译（纯命令行）",
    )
    parser.add_argument("text", nargs="?", help="要翻译的英文；不填则读文件或标准输入")
    parser.add_argument("-f", "--file", help="读取英文文本文件（UTF-8）")
    parser.add_argument("--server", help="MTranServer 地址，默认 http://127.0.0.1:8989")
    parser.add_argument("--token", help="MT_API_TOKEN；也可用环境变量")
    parser.add_argument("--timeout", type=float, default=30.0, help="请求超时秒数，默认 30")
    parser.add_argument("--batch-size", type=int, default=32, help="批量翻译句数，默认 32")
    parser.add_argument("--source", default="en", help="源语言代码，默认 en")
    parser.add_argument("--target", default="zh-Hans", help="目标语言代码，默认 zh-Hans")
    parser.add_argument("--no-correct", action="store_true", help="跳过本地拼写/语法纠错")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON")
    parser.add_argument("--stats", action="store_true", help="在普通输出中显示耗时统计")
    parser.add_argument("--check", action="store_true", help="只检查 MTranServer 连接")
    parser.add_argument("--no-autostart", action="store_true", help="不要自动启动项目内置的 MTranServer")
    parser.add_argument("--encoding", default="utf-8-sig", help="文件编码，默认 utf-8-sig")
    parser.add_argument("--version", action="version", version=f"zhtrans {VERSION}")
    return parser


def main(argv: Optional[list] = None) -> int:
    _setup_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)

    client = MTranClient(
        base_url=args.server,
        token=args.token,
        timeout=args.timeout,
        auto_start=not args.no_autostart,
    )
    try:
        if args.check:
            client.ensure_server()
            data = client.languages()
            if args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                print(f"MTranServer 可用：{client.base_url}")
                if isinstance(data, dict):
                    languages = data.get("languages") or []
                    pairs = data.get("pairs") or []
                    print(f"语言：{len(languages)} 种；语言对：{len(pairs)} 个")
                    en_zh = any(
                        p.get("from") == "en" and p.get("to") == "zh-Hans"
                        for p in pairs
                        if isinstance(p, dict)
                    )
                    print("en -> zh-Hans：" + ("已准备" if en_zh else "未检测到"))
            return 0

        engine = TranslationEngine(
            client=client,
            lexicon=Lexicon(),
            batch_size=args.batch_size,
        )
        if not args.text and not args.file and sys.stdin.isatty():
            return _interactive(engine, args)

        text = _read_input(args)
        if text is None:
            return 2
        if not text.strip():
            print("没有输入文本。", file=sys.stderr)
            return 2

        result = engine.translate(
            text,
            correct=not args.no_correct,
            source=args.source,
            target=args.target,
        )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            _print_human(result, show_stats=args.stats)
        return 0
    except MTranUnavailable as exc:
        print(f"[无法连接 MTranServer] {client.base_url}", file=sys.stderr)
        print(f"原因：{exc}", file=sys.stderr)
        print("", file=sys.stderr)
        print("项目已自带 MTranServer（vendor/），通常会自动启动。", file=sys.stderr)
        print("手动启动：start_mtran.cmd；前台调试：mtran.cmd", file=sys.stderr)
        print("若使用外部服务：--server http://127.0.0.1:8989", file=sys.stderr)
        print("也可设置环境变量 MTRAN_SERVER_URL / MT_API_TOKEN。", file=sys.stderr)
        return 2
    except MTranError as exc:
        print(f"[MTranServer 返回错误] {exc}", file=sys.stderr)
        if exc.body:
            print(exc.body[:1000], file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print("\n已中断。", file=sys.stderr)
        return 130
    finally:
        client.close()


def _setup_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def _read_input(args: argparse.Namespace) -> Optional[str]:
    if args.text:
        return args.text
    if args.file:
        path = Path(args.file)
        try:
            return path.read_text(encoding=args.encoding)
        except OSError as exc:
            print(f"无法读取文件：{exc}", file=sys.stderr)
            return None
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return None


def _interactive(engine: TranslationEngine, args: argparse.Namespace) -> int:
    print("MTranServer 英译中（输入 :q 退出，输入 :paste 粘贴多行）")
    while True:
        try:
            line = input("英文> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        command = line.strip().lower()
        if command in (":q", "quit", "exit"):
            return 0
        if command == ":paste":
            print("粘贴多行，单独输入 :end 结束：")
            lines = []
            while True:
                try:
                    part = input()
                except EOFError:
                    break
                if part.strip().lower() == ":end":
                    break
                lines.append(part)
            text = "\n".join(lines)
        else:
            text = line
        if not text.strip():
            continue
        try:
            result = engine.translate(
                text,
                correct=not args.no_correct,
                source=args.source,
                target=args.target,
            )
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                _print_human(result, show_stats=args.stats)
        except MTranUnavailable as exc:
            print(f"[无法连接 MTranServer] {exc}", file=sys.stderr)
        except MTranError as exc:
            print(f"[翻译失败] {exc}", file=sys.stderr)
        print()


def _print_human(result: dict, show_stats: bool = False) -> None:
    print("=== 译文 ===")
    print(result["translation"] or "(空)")
    print()
    if result["corrected"] and result["corrected"] != result["source"].strip():
        print("=== 订正后的英文 ===")
        print(result["corrected"])
        print()

    issues = result.get("issues", [])
    print("=== 错词 / 病句 ===")
    if not issues:
        print("未发现明显错词或病句。")
    else:
        for n, issue in enumerate(issues, 1):
            sentence_no = issue.get("segment", 0) + 1
            kind = {
                "spelling": "拼写",
                "grammar": "语法",
                "punctuation": "标点",
                "unknown": "未收录",
            }.get(issue.get("type", ""), issue.get("type", "问题"))
            message = issue.get("message", "")
            original = issue.get("original", "")
            suggestion = issue.get("suggestion", "")
            if original and suggestion and "→" not in message:
                message = f"{message}（{original} → {suggestion}）"
            print(f"{n}. [{kind}] 第{sentence_no}句：{message}")

    unknown = result.get("unknown", [])
    if unknown:
        print()
        print("未收录词（保留原文，未自动改写）：" + "、".join(unknown))

    if show_stats:
        stats = result.get("stats", {})
        print()
        print(
            "=== 统计 ===\n"
            f"后端：{stats.get('backend')} {stats.get('server')}\n"
            f"句子：{stats.get('sentences')}  词：{stats.get('words')}  "
            f"问题：{stats.get('issues')}  耗时：{stats.get('elapsed_ms')} ms"
        )
