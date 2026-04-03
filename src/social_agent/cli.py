"""
cli.py - Giao diện dòng lệnh cho Social Agent (Facebook + LinkedIn)
Dùng Click + Rich để cung cấp UX đẹp trên terminal
"""

import random
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()


def get_agent(config: str):
    """Khởi tạo agent từ config path."""
    from social_agent.agent import SocialAgent
    return SocialAgent(config_path=config)


# ============================================================
# CLI Group chính
# ============================================================

@click.group()
@click.option("--config", default="config.yaml", show_default=True, help="Đường dẫn đến config.yaml")
@click.pass_context
def cli(ctx, config):
    """
    Social Agent - Tự động tạo và đăng nội dung lên Facebook & LinkedIn.

    Các lệnh chính:
      run        - Chạy scheduler daemon
      post       - Đăng bài ngay lập tức lên 1 target
      cross-post - Đăng cùng content lên nhiều platform (generate 1 lần)
      preview    - Xem trước nội dung cho 1 platform
      preview-all - Xem trước cả Facebook lẫn LinkedIn cùng lúc
      stats      - Thống kê lịch sử đăng bài
      validate   - Kiểm tra cấu hình và kết nối
    """
    ctx.ensure_object(dict)
    ctx.obj["config"] = config


# ============================================================
# run - Khởi động scheduler daemon
# ============================================================

@cli.command()
@click.pass_context
def run(ctx):
    """Khởi động scheduler daemon - đăng bài tự động theo lịch trong config.yaml."""
    config = ctx.obj["config"]
    console.print(Panel.fit(
        "[bold green]Facebook Auto-Post Agent[/] đang khởi động...\n"
        f"Config: [cyan]{config}[/]\n"
        "Nhấn [bold]Ctrl+C[/] để dừng.",
        title="🤖 Scheduler",
        border_style="green",
    ))
    try:
        agent = get_agent(config)
        agent.run_scheduled()
    except FileNotFoundError as e:
        console.print(f"[red]Lỗi:[/] {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Scheduler đã dừng.[/]")


# ============================================================
# post - Đăng bài ngay lập tức
# ============================================================

@cli.command()
@click.option("-t", "--target", required=True, help="ID của target (vd: fastdx_page)")
@click.option("-p", "--topic", default=None, help="ID của topic (random nếu không chỉ định)")
@click.option("-f", "--format", "fmt", default=None, help="ID của format (random nếu không chỉ định)")
@click.option("--image", default=None, help="Đường dẫn đến ảnh đính kèm (tuỳ chọn)")
@click.option("--no-image", "no_image", is_flag=True, help="Đăng text-only, không generate ảnh AI")
@click.option("--dry-run", is_flag=True, help="Chỉ generate + hiển thị, không đăng thật")
@click.pass_context
def post(ctx, target, topic, fmt, image, no_image, dry_run):
    """Đăng bài ngay lập tức lên target được chỉ định."""
    config = ctx.obj["config"]

    if dry_run:
        console.print("[yellow]Chế độ dry-run: không đăng lên Facebook[/]")

    try:
        agent = get_agent(config)

        if dry_run:
            if not topic:
                targets_cfg = agent._targets.get(target, {})
                topic = random.choice(targets_cfg.get("topics", list(agent._topics.keys())))
            if not fmt:
                targets_cfg = agent._targets.get(target, {})
                fmt = random.choice(targets_cfg.get("formats", list(agent._formats.keys())))
            content = agent.preview(topic, fmt)
            console.print(Panel(
                content,
                title=f"[cyan]Preview[/] | topic=[yellow]{topic}[/] format=[yellow]{fmt}[/]",
                border_style="cyan",
            ))
            return

        with console.status(f"[cyan]Đang tạo và đăng bài lên [bold]{target}[/]..."):
            result = agent.post_now(
                target_id=target,
                topic_id=topic,
                format_id=fmt,
                image_path=image,
                no_image=no_image,
            )

        console.print(Panel(
            f"[green]✓ Đăng thành công![/]\n\n"
            f"[dim]Post ID:[/] {result.get('post_id', 'N/A')}\n"
            f"[dim]URL:[/] {result.get('post_url', 'N/A')}\n\n"
            f"[bold]Nội dung:[/]\n{result.get('content', '')}",
            title="✅ Kết quả",
            border_style="green",
        ))

    except ValueError as e:
        console.print(f"[red]Lỗi cấu hình:[/] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Lỗi:[/] {e}")
        sys.exit(1)


# ============================================================
# preview - Xem trước nội dung
# ============================================================

@cli.command()
@click.option("-p", "--topic", required=True, help="ID của topic (vd: ai_vietnam)")
@click.option("-f", "--format", "fmt", required=True, help="ID của format (vd: thought_leadership)")
@click.option("--platform", default="facebook", show_default=True, help="Platform: facebook | linkedin")
@click.pass_context
def preview(ctx, topic, fmt, platform):
    """Generate nội dung và hiển thị mà không đăng."""
    config = ctx.obj["config"]
    try:
        agent = get_agent(config)
        with console.status(f"[cyan]Đang tạo nội dung cho {platform}..."):
            content = agent.preview(topic, fmt, platform=platform)

        platform_color = "blue" if platform == "linkedin" else "cyan"
        console.print(Panel(
            content,
            title=f"[{platform_color}]Preview {platform.upper()}[/] | topic=[yellow]{topic}[/] | format=[yellow]{fmt}[/]",
            border_style=platform_color,
            padding=(1, 2),
        ))
        console.print(f"[dim]Độ dài: {len(content)} ký tự[/]")

    except Exception as e:
        console.print(f"[red]Lỗi:[/] {e}")
        sys.exit(1)


@cli.command("preview-all")
@click.option("-p", "--topic", required=True, help="ID của topic (vd: ai_vietnam)")
@click.option("-f", "--format", "fmt", required=True, help="ID của format (vd: thought_leadership)")
@click.pass_context
def preview_all(ctx, topic, fmt):
    """Generate content 1 lần, hiển thị cả Facebook lẫn LinkedIn để so sánh."""
    config = ctx.obj["config"]
    try:
        agent = get_agent(config)
        with console.status("[cyan]Đang tạo nội dung (generate 1 lần cho cả 2 platforms)..."):
            result = agent.preview_all_platforms(topic, fmt)

        console.print(Panel(
            result["facebook"],
            title=f"[cyan]Facebook[/] | topic=[yellow]{topic}[/] | format=[yellow]{fmt}[/] | [dim]{len(result['facebook'])} ký tự[/]",
            border_style="cyan",
            padding=(1, 2),
        ))
        console.print(Panel(
            result["linkedin"],
            title=f"[blue]LinkedIn[/] | topic=[yellow]{topic}[/] | format=[yellow]{fmt}[/] | [dim]{len(result['linkedin'])} ký tự[/]",
            border_style="blue",
            padding=(1, 2),
        ))

    except Exception as e:
        console.print(f"[red]Lỗi:[/] {e}")
        sys.exit(1)


@cli.command("cross-post")
@click.option("-g", "--group", "group_id", default=None, help="ID của cross-post group (vd: all_platforms)")
@click.option("-t", "--targets", default=None, help="Danh sách target IDs cách nhau bằng dấu phẩy (vd: fastdx_page,linkedin_profile)")
@click.option("-p", "--topic", default=None, help="ID của topic (random nếu không chỉ định)")
@click.option("-f", "--format", "fmt", default=None, help="ID của format (random nếu không chỉ định)")
@click.option("--image", default=None, help="Đường dẫn ảnh đính kèm")
@click.pass_context
def cross_post(ctx, group_id, targets, topic, fmt, image):
    """Đăng cùng content lên nhiều platform - LLM chỉ được gọi 1 lần."""
    config = ctx.obj["config"]
    if not group_id and not targets:
        console.print("[red]Cần chỉ định --group hoặc --targets[/]")
        sys.exit(1)

    target_ids = [t.strip() for t in targets.split(",")] if targets else None

    try:
        agent = get_agent(config)
        label = group_id or targets
        with console.status(f"[cyan]Cross-posting lên [{label}]..."):
            results = agent.cross_post(
                group_id=group_id,
                target_ids=target_ids,
                topic_id=topic,
                format_id=fmt,
                image_path=image,
            )

        table = Table(title="Cross-Post Results", box=box.ROUNDED, border_style="green")
        table.add_column("Target", style="bold yellow")
        table.add_column("Platform", style="cyan")
        table.add_column("Kết quả", justify="center")
        table.add_column("URL / Lỗi")

        for target_id, result in results.items():
            if result.get("success"):
                table.add_row(
                    target_id,
                    result.get("platform", ""),
                    "[green]✓ OK[/]",
                    result.get("post_url", ""),
                )
            else:
                table.add_row(
                    target_id,
                    "",
                    "[red]✗ Lỗi[/]",
                    result.get("error", ""),
                )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Lỗi:[/] {e}")
        sys.exit(1)


# ============================================================
# list-topics / list-targets
# ============================================================

@cli.command("list-topics")
@click.pass_context
def list_topics(ctx):
    """Hiển thị danh sách topics đã cấu hình."""
    config = ctx.obj["config"]
    try:
        agent = get_agent(config)
        topics = agent.generator.list_topics()

        table = Table(
            title="📋 Topics đã cấu hình",
            box=box.ROUNDED,
            border_style="cyan",
            show_lines=True,
        )
        table.add_column("ID", style="bold yellow", no_wrap=True)
        table.add_column("Tên", style="bold")
        table.add_column("Mô tả", style="dim")
        table.add_column("Keywords", style="green")

        for t in topics:
            table.add_row(
                t["id"],
                t["name"],
                t["description"][:60] + "..." if len(t["description"]) > 60 else t["description"],
                ", ".join(t.get("keywords", [])[:4]),
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Lỗi:[/] {e}")
        sys.exit(1)


@cli.command("list-targets")
@click.pass_context
def list_targets(ctx):
    """Hiển thị danh sách targets (Pages, Groups, Profile) đã cấu hình."""
    config = ctx.obj["config"]
    try:
        agent = get_agent(config)

        table = Table(
            title="🎯 Targets đã cấu hình",
            box=box.ROUNDED,
            border_style="green",
            show_lines=True,
        )
        table.add_column("ID", style="bold yellow", no_wrap=True)
        table.add_column("Tên", style="bold")
        table.add_column("Loại", style="cyan")
        table.add_column("Lịch", style="magenta")
        table.add_column("Trạng thái", justify="center")

        for tid, t in agent._targets.items():
            status = "[green]✓ Bật[/]" if t.get("enabled", True) else "[red]✗ Tắt[/]"
            table.add_row(
                tid,
                t.get("name", tid),
                t.get("type", "page").upper(),
                t.get("schedule", "—"),
                status,
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Lỗi:[/] {e}")
        sys.exit(1)


# ============================================================
# validate
# ============================================================

@cli.command()
@click.pass_context
def validate(ctx):
    """Kiểm tra cấu hình config.yaml và kết nối Facebook API."""
    config = ctx.obj["config"]
    console.print("[cyan]Đang kiểm tra cấu hình...[/]")

    try:
        agent = get_agent(config)

        table = Table(
            title="🔍 Kết quả kiểm tra",
            box=box.ROUNDED,
            border_style="blue",
            show_lines=True,
        )
        table.add_column("Target", style="bold yellow")
        table.add_column("Loại", style="cyan")
        table.add_column("Trạng thái", justify="center")
        table.add_column("Chi tiết")

        results = agent.validate()
        all_ok = True

        for target_id, result in results.items():
            target = agent._targets.get(target_id, {})
            target_type = target.get("type", "page").upper()
            is_valid = result.get("valid", False)
            all_ok = all_ok and is_valid

            if is_valid:
                status = "[green]✓ OK[/]"
                detail = result.get("name") or result.get("note") or "Kết nối thành công"
            else:
                status = "[red]✗ Lỗi[/]"
                detail = result.get("error", "Không xác định")

            table.add_row(target_id, target_type, status, detail)

        console.print(table)

        llm = agent.config.get("llm", {})
        provider = llm.get("provider", "anthropic")
        model = llm.get("model", "N/A")
        console.print(f"\n[dim]LLM Provider:[/] {provider} | [dim]Model:[/] {model}")

        if all_ok:
            console.print("\n[green]✅ Tất cả OK. Sẵn sàng đăng bài![/]")
        else:
            console.print("\n[yellow]⚠️  Một số target chưa sẵn sàng. Kiểm tra lại .env và config.yaml[/]")

    except Exception as e:
        console.print(f"[red]Lỗi:[/] {e}")
        sys.exit(1)


# ============================================================
# stats
# ============================================================

@cli.command()
@click.option("--limit", default=20, show_default=True, help="Số lượng bài gần nhất hiển thị")
@click.pass_context
def stats(ctx, limit):
    """Hiển thị thống kê và lịch sử đăng bài từ audit log."""
    config = ctx.obj["config"]
    try:
        agent = get_agent(config)
        stats_data = agent.get_stats()
        history = agent.get_history(limit=limit)

        console.print(Panel(
            f"[bold]Tổng bài đăng:[/] {stats_data['total']}\n"
            f"[green]Thành công:[/] {stats_data['success']}\n"
            f"[red]Thất bại:[/] {stats_data['failed']}",
            title="📊 Tổng quan",
            border_style="blue",
        ))

        if stats_data["by_target"]:
            t_table = Table(title="Theo Target", box=box.SIMPLE, border_style="dim")
            t_table.add_column("Target")
            t_table.add_column("Số bài", justify="right")
            for k, v in sorted(stats_data["by_target"].items(), key=lambda x: -x[1]):
                t_table.add_row(k, str(v))
            console.print(t_table)

        if history:
            h_table = Table(
                title=f"📝 {limit} bài gần nhất",
                box=box.ROUNDED,
                border_style="cyan",
                show_lines=False,
            )
            h_table.add_column("Thời gian", style="dim", no_wrap=True)
            h_table.add_column("Target", style="yellow")
            h_table.add_column("Topic")
            h_table.add_column("Format")
            h_table.add_column("KQ", justify="center")

            for entry in reversed(history):
                ts = entry.get("timestamp", "")[:16]
                status = "[green]✓[/]" if entry.get("success") else "[red]✗[/]"
                h_table.add_row(
                    ts,
                    entry.get("target_id", ""),
                    entry.get("topic_id", ""),
                    entry.get("format_id", ""),
                    status,
                )

            console.print(h_table)
        else:
            console.print("[dim]Chưa có lịch sử đăng bài.[/]")

    except Exception as e:
        console.print(f"[red]Lỗi:[/] {e}")
        sys.exit(1)


# ============================================================
# token - Lấy Page Token vĩnh viễn từ Facebook
# ============================================================

@cli.command("token")
@click.option("--app-id", default=None, help="Facebook App ID (bỏ qua nếu đã có trong .env)")
@click.option("--app-secret", default=None, help="Facebook App Secret (bỏ qua để nhập ẩn)")
@click.option("--user-token", default=None, help="Short-lived User Token từ Graph API Explorer")
@click.option("--refresh-all", is_flag=True,
              help="Tự động gia hạn tokens dùng credentials đã lưu trong .env (không cần nhập lại)")
@click.option("--save", is_flag=True, default=True,
              help="Tự động ghi tokens mới vào .env (mặc định: bật)")
def token(app_id, app_secret, user_token, refresh_all, save):
    """
    Đổi/gia hạn Facebook Page Tokens và tự ghi vào .env.

    Lần đầu setup:
    \b
    1. Vào https://developers.facebook.com/tools/explorer
    2. Chọn App → Get User Access Token
    3. Permissions: pages_manage_posts, pages_read_engagement, pages_show_list
    4. Chạy: social-agent token --app-id APP_ID --user-token EAA...
    → Tokens được ghi vào .env tự động, không cần copy tay.

    Lần sau (gia hạn — chỉ cần 1 lệnh):
    \b
    social-agent token --refresh-all
    → Dùng FB_APP_ID, FB_APP_SECRET, FB_USER_TOKEN đã lưu trong .env để gia hạn tự động.
    """
    import os
    from social_agent.platforms.facebook import FacebookAPI
    from social_agent.utils.dotenv_writer import update_env_file
    from dotenv import load_dotenv
    load_dotenv(override=True)

    fb = FacebookAPI()

    # --- Chế độ refresh-all: đọc credentials từ .env ---
    if refresh_all:
        app_id = app_id or os.getenv("FB_APP_ID")
        app_secret = app_secret or os.getenv("FB_APP_SECRET")
        user_token = user_token or os.getenv("FB_USER_TOKEN")

        missing = [k for k, v in {"FB_APP_ID": app_id, "FB_APP_SECRET": app_secret,
                                   "FB_USER_TOKEN": user_token}.items() if not v]
        if missing:
            console.print(
                f"[red]Thiếu credentials trong .env:[/] {', '.join(missing)}\n"
                "[dim]Lần đầu dùng lệnh không có --refresh-all để setup.[/]"
            )
            sys.exit(1)

        console.print("[cyan]Đang gia hạn tokens tự động...[/]")
        try:
            result = fb.refresh_page_tokens(app_id, app_secret, user_token)
        except Exception as e:
            console.print(f"[red]Lỗi khi refresh:[/] {e}")
            sys.exit(1)

        _show_and_save_tokens(result, app_id, app_secret, save)
        return

    # --- Lần đầu setup: cần app-id + user-token ---
    if not app_id:
        app_id = click.prompt("App ID")
    if not app_secret:
        app_secret = os.getenv("FB_APP_SECRET") or click.prompt("App Secret", hide_input=True)
    if not user_token:
        console.print(
            "[yellow]Lấy User Token tại:[/] https://developers.facebook.com/tools/explorer\n"
            "[dim]Permissions: pages_manage_posts, pages_read_engagement, pages_show_list[/]"
        )
        user_token = click.prompt("User Token")

    console.print("[cyan]Đang xử lý tokens...[/]")
    try:
        result = fb.refresh_page_tokens(app_id, app_secret, user_token)
    except Exception as e:
        console.print(f"[red]Lỗi:[/] {e}")
        sys.exit(1)

    _show_and_save_tokens(result, app_id, app_secret, save)


def _show_and_save_tokens(result: dict, app_id: str, app_secret: str, save: bool):
    """Hiển thị kết quả và ghi vào .env."""
    from social_agent.utils.dotenv_writer import update_env_file

    pages = result["pages"]
    long_token = result["long_lived_user_token"]

    if not pages:
        console.print("[yellow]Không tìm thấy Page nào. Token có permission pages_show_list chưa?[/]")
        sys.exit(1)

    table = Table(title="🔑 Page Tokens (không hết hạn)", box=box.ROUNDED,
                  border_style="green", show_lines=True)
    table.add_column("Page Name", style="bold yellow")
    table.add_column("Page ID", style="cyan")
    table.add_column("Env Key gợi ý")
    for page in pages:
        env_key = page["name"].upper().replace(" ", "_").replace("-", "_") + "_TOKEN"
        table.add_row(page["name"], page["id"], env_key)
    console.print(table)

    if save:
        # Map page_id → env key dựa theo config.yaml hiện tại
        import yaml
        from pathlib import Path
        config_path = Path("config.yaml")
        page_id_to_env: dict[str, str] = {}
        if config_path.exists():
            cfg = yaml.safe_load(config_path.read_text())
            for t in cfg.get("targets", []):
                raw_token = t.get("access_token", "")
                # "${FASTDX_PAGE_TOKEN}" → "FASTDX_PAGE_TOKEN"
                import re
                m = re.match(r"\$\{(\w+)\}", raw_token)
                if m:
                    page_id_to_env[str(t.get("target_id", ""))] = m.group(1)

        updates: dict = {
            "FB_APP_ID": app_id,
            "FB_APP_SECRET": app_secret,
            "FB_USER_TOKEN": long_token,
        }
        for page in pages:
            env_key = page_id_to_env.get(page["id"])
            if env_key:
                updates[env_key] = page["token"]
            else:
                # Fallback: thêm key mới theo tên page
                fallback = page["name"].upper().replace(" ", "_").replace("-", "_") + "_TOKEN"
                updates[fallback] = page["token"]

        updated = update_env_file(updates)
        console.print(
            f"\n[green]✓ Đã ghi {len(updated)} keys vào .env:[/] "
            + ", ".join(f"[yellow]{k}[/]" for k in updated)
        )
        console.print("[dim]Lần sau chỉ cần: social-agent token --refresh-all[/]")
    else:
        console.print("\n[dim]Dùng --save để tự động ghi vào .env.[/]")


# ============================================================
# review - Xem và duyệt bài trong review queue
# ============================================================

@cli.command("review")
@click.option("--approve", "entry_id_approve", default=None, metavar="ID",
              help="Approve và đăng bài có ID này")
@click.option("--reject", "entry_id_reject", default=None, metavar="ID",
              help="Reject bài có ID này")
@click.option("--reason", "reject_reason", default=None, metavar="TEXT",
              help="Lý do từ chối (dùng để AI học hỏi và không lặp lại lỗi)")
@click.pass_context
def review(ctx, entry_id_approve, entry_id_reject, reject_reason):
    """
    Xem danh sách bài chờ duyệt (review queue) và approve/reject.

    Ví dụ:
    \b
    social-agent review                      # Xem tất cả bài đang chờ
    social-agent review --approve abc123     # Approve và đăng ngay
    social-agent review --reject  abc123     # Reject, không đăng
    social-agent review --reject  abc123 --reason "Quá nhiều từ chuyên môn AI"
    """
    config = ctx.obj["config"]
    try:
        agent = get_agent(config)

        if entry_id_approve:
            with console.status(f"[green]Đang đăng bài {entry_id_approve}..."):
                result = agent.approve_review(entry_id_approve)
            console.print(Panel(
                f"[green]✓ Đã đăng![/]\n\n"
                f"[dim]Post ID:[/] {result.get('post_id', 'N/A')}\n"
                f"[dim]URL:[/] {result.get('post_url', 'N/A')}\n\n"
                + f"{result.get('content', '')}",
                title=f"✅ Approved: {entry_id_approve}",
                border_style="green",
            ))
            return

        if entry_id_reject:
            agent.reject_review(entry_id_reject, reason=reject_reason)
            msg = f"[yellow]Đã reject bài {entry_id_reject}.[/]"
            if reject_reason:
                msg += f" [dim]Lý do AI đã ghi nhận: {reject_reason}[/]"
            console.print(msg)
            return

        pending = agent.list_review_queue()
        if not pending:
            console.print("[dim]Không có bài nào đang chờ duyệt.[/]")
            return

        console.print(f"[bold]{len(pending)} bài đang chờ duyệt:[/]\n")
        for entry in pending:
            ts = entry.get("created_at", "")[:16]
            console.print(Panel(
                f"[dim]Tạo lúc:[/] {ts}  |  "
                f"[dim]Target:[/] [yellow]{entry['target_id']}[/]  |  "
                f"[dim]Topic:[/] {entry['topic_id']}  |  "
                f"[dim]Format:[/] {entry['format_id']}  |  "
                f"[dim]Platform:[/] {entry.get('platform', '')}\n\n"
                + (f"[dim]Research summary:[/] {entry['brief_summary'][:120]}…\n\n"
                   if entry.get("brief_summary") else "")
                + f"{entry['content']}",
                title=f"[cyan]ID: {entry['id']}[/]",
                border_style="cyan",
                padding=(1, 2),
            ))
            console.print(
                f"  → [green]social-agent review --approve {entry['id']}[/]  "
                f"[red]social-agent review --reject {entry['id']}[/]\n"
            )

    except ValueError as e:
        console.print(f"[red]Lỗi:[/] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Lỗi:[/] {e}")
        sys.exit(1)


# ============================================================
# research - Research + generate + post từ nhiều nguồn
# ============================================================

@cli.command("research")
@click.option("--topic", required=True, help="Mô tả chủ đề / góc nhìn muốn viết")
@click.option("--url", "urls", multiple=True, metavar="URL",
              help="URL làm nguồn (có thể dùng nhiều lần: --url ... --url ...)")
@click.option("--fb-page", "fb_pages", multiple=True, metavar="PAGE_ID",
              help="Facebook page ID/username làm nguồn (vd: fastdx.dev)")
@click.option("--linkedin-company", "linkedin_companies", multiple=True, metavar="COMPANY",
              help="LinkedIn company vanity name làm nguồn (vd: fastdx)")
@click.option("-t", "--target", default=None, help="Target để đăng bài (bỏ qua nếu dùng --dry-run)")
@click.option("-f", "--format", "fmt", default=None,
              help="Format nội dung (thought_leadership, quick_insight, story_post, engagement_post)")
@click.option("--save-brief", default=None, metavar="FILE",
              help="Lưu ResearchBrief ra file JSON (vd: brief.json)")
@click.option("--dry-run", is_flag=True, help="Chỉ generate + hiển thị, không đăng thật")
@click.pass_context
def research(ctx, topic, urls, fb_pages, linkedin_companies, target, fmt, save_brief, dry_run):
    """
    Research từ URLs / Facebook Pages / LinkedIn, tóm tắt bằng AI, generate và đăng bài.

    Ví dụ:
    \b
    # Dry-run với 1 URL
    social-agent research --topic "AI trong logistics Việt Nam" \\
        --url https://example.com/article \\
        --dry-run

    \b
    # Lấy từ nhiều nguồn, đăng lên fastdx_page
    social-agent research \\
        --topic "Xu hướng DX 2025" \\
        --url https://blog1.com --url https://blog2.com \\
        --fb-page fastdx.dev \\
        --linkedin-company fastdx \\
        --target fastdx_page \\
        --format thought_leadership
    """
    config = ctx.obj["config"]

    if not dry_run and not target:
        console.print("[red]Cần chỉ định --target khi không dùng --dry-run[/]")
        sys.exit(1)

    if not any([urls, fb_pages, linkedin_companies]):
        console.print("[yellow]Chưa có nguồn nào. Dùng --url, --fb-page hoặc --linkedin-company.[/]")
        sys.exit(1)

    try:
        agent = get_agent(config)

        sources_lines = []
        for u in urls:
            sources_lines.append(f"  [cyan]Web:[/]      {u}")
        for p in fb_pages:
            sources_lines.append(f"  [blue]Facebook:[/] {p}")
        for c in linkedin_companies:
            sources_lines.append(f"  [blue]LinkedIn:[/] {c}")

        console.print(Panel(
            f"[bold]Chủ đề:[/] {topic}\n\n"
            f"[bold]Nguồn ({len(urls) + len(fb_pages) + len(linkedin_companies)}):[/]\n"
            + "\n".join(sources_lines),
            title="[cyan]Research Agent[/]",
            border_style="cyan",
        ))

        with console.status("[cyan]Đang fetch và phân tích các nguồn (Gemini call #1)..."):
            result = agent.research_and_post(
                topic_description=topic,
                target_id=target or "__dry_run__",
                format_id=fmt,
                urls=list(urls),
                fb_pages=list(fb_pages),
                linkedin_companies=list(linkedin_companies),
                dry_run=dry_run,
            )

        brief = result.get("brief", {})

        fetched = brief.get("sources_fetched", [])
        failed = brief.get("sources_failed", [])
        insights = brief.get("key_insights", [])
        angles = brief.get("content_angles", [])

        fetch_info = ""
        if fetched:
            fetch_info += f"[green]✓ Fetched:[/] {', '.join(fetched)}\n"
        if failed:
            fetch_info += f"[red]✗ Failed:[/] {', '.join(failed)}\n"
        if insights:
            fetch_info += "\n[bold]Key Insights:[/]\n" + "\n".join(f"  • {i}" for i in insights)
        if angles:
            fetch_info += "\n\n[bold]Góc tiếp cận gợi ý:[/]\n" + "\n".join(f"  → {a}" for a in angles)

        if fetch_info:
            console.print(Panel(fetch_info.strip(), title="[dim]Research Brief[/]", border_style="dim"))

        platform_color = "blue" if result.get("platform") == "linkedin" else "cyan"
        console.print(Panel(
            result.get("content", ""),
            title=(
                f"[{platform_color}]Generated Content[/] | "
                f"format=[yellow]{result.get('format_id', '')}[/] | "
                f"[dim]{len(result.get('content', ''))} ký tự[/]"
            ),
            border_style=platform_color,
            padding=(1, 2),
        ))

        if dry_run:
            console.print("[yellow]Dry-run: không đăng lên mạng xã hội.[/]")
        elif result.get("queued"):
            review_id = result.get("review_id", "")
            console.print(Panel(
                f"[yellow]Target này bật review_mode → bài đã được đưa vào hàng chờ duyệt.[/]\n\n"
                f"[dim]Review ID:[/] [bold]{review_id}[/]\n\n"
                f"Duyệt bài:  [green]social-agent review --approve {review_id}[/]\n"
                f"Từ chối:    [red]social-agent review --reject {review_id}[/]\n"
                f"Xem tất cả: [cyan]social-agent review[/]",
                title="⏳ Chờ duyệt",
                border_style="yellow",
            ))
        else:
            console.print(Panel(
                f"[green]✓ Đăng thành công![/]\n\n"
                f"[dim]Post ID:[/] {result.get('post_id', 'N/A')}\n"
                f"[dim]URL:[/] {result.get('post_url', 'N/A')}",
                title="✅ Kết quả",
                border_style="green",
            ))

        if save_brief:
            import json as _json
            Path(save_brief).write_text(
                _json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            console.print(f"[dim]Brief đã lưu: {save_brief}[/]")

    except ValueError as e:
        console.print(f"[red]Lỗi cấu hình:[/] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Lỗi:[/] {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli(obj={})


# ============================================================
# discover - Trigger dynamic source discovery cho 1 topic
# ============================================================

@cli.command("discover")
@click.option("-t", "--topic", "topic_id", default=None,
              help="Topic ID cần discover (vd: ai_vietnam). Bỏ qua để chạy tất cả.")
@click.option("--force", is_flag=True,
              help="Force re-discover ngay cả khi registry đã có đủ sources.")
@click.pass_context
def discover(ctx, topic_id, force):
    """
    Tự động tìm Facebook pages và URLs mới nhất cho topic, lưu vào registry.

    \b
    social-agent discover -t ai_vietnam             # Discover 1 topic
    social-agent discover                           # Discover tất cả topics
    social-agent discover -t dx_consulting --force  # Force re-discover
    """
    import os
    from dotenv import load_dotenv
    load_dotenv()
    config = ctx.obj["config"]

    try:
        from social_agent.research.discovery import DynamicSourceResolver
        import yaml

        with open(config, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        gemini_key = os.environ.get("GEMINI_API_KEY")
        if not gemini_key:
            console.print("[red]Thiếu GEMINI_API_KEY trong .env[/]")
            sys.exit(1)

        fb_token = os.environ.get("FASTDX_PAGE_TOKEN")
        resolver = DynamicSourceResolver(
            gemini_api_key=gemini_key,
            fb_access_token=fb_token,
        )

        topics = cfg.get("topics", [])
        if topic_id:
            topics = [t for t in topics if t["id"] == topic_id]
            if not topics:
                console.print(f"[red]Topic không tồn tại: {topic_id}[/]")
                sys.exit(1)

        for topic_cfg in topics:
            tid = topic_cfg["id"]
            research_cfg = topic_cfg.get("research", {})

            console.print(f"\n[cyan]Discovering sources:[/] [bold yellow]{tid}[/]")
            with console.status(f"[dim]Đang tìm ({topic_cfg.get('name', tid)})...[/]"):
                resolved = resolver.resolve(
                    topic_id=tid,
                    topic_cfg=topic_cfg,
                    seed_urls=research_cfg.get("urls", []),
                    seed_fb_pages=research_cfg.get("fb_pages", []),
                    force_discover=force,
                )

            tbl = Table(box=box.SIMPLE, show_header=False, border_style="dim")
            tbl.add_column("Type", width=10)
            tbl.add_column("Source")
            for u in resolved["urls"]:
                tbl.add_row("🌐 Web", u)
            for p in resolved["fb_pages"]:
                tbl.add_row("📘 FB", p)

            if resolved["urls"] or resolved["fb_pages"]:
                console.print(tbl)
                console.print(
                    f"  [green]✓[/] {len(resolved['urls'])} URLs + "
                    f"{len(resolved['fb_pages'])} FB pages → saved to registry"
                )
            else:
                console.print("  [yellow]Không tìm được nguồn nào.[/]")

    except Exception as e:
        console.print(f"[red]Lỗi:[/] {e}")
        sys.exit(1)


# ============================================================
# sources - Xem source registry
# ============================================================

@cli.command("sources")
@click.option("-t", "--topic", "topic_id", default=None, help="Filter theo topic ID")
@click.option("--all", "show_all", is_flag=True, help="Hiện cả sources inactive")
@click.pass_context
def sources_cmd(ctx, topic_id, show_all):
    """Xem danh sách sources trong registry — ranked theo success rate."""
    try:
        from social_agent.research.discovery import SourceRegistry
        registry = SourceRegistry()

        with registry._connect() as conn:
            q = """
                SELECT topic_id, source_type, identifier, display_name,
                       success_count, fail_count, is_active,
                       substr(discovered_at, 1, 10) as disc_date
                FROM discovered_sources
            """
            params = []
            clauses = []
            if topic_id:
                clauses.append("topic_id=?")
                params.append(topic_id)
            if not show_all:
                clauses.append("is_active=1")
            if clauses:
                q += " WHERE " + " AND ".join(clauses)
            q += " ORDER BY topic_id, source_type, (success_count - fail_count) DESC"
            rows = [dict(r) for r in conn.execute(q, params).fetchall()]

        if not rows:
            console.print(
                "[dim]Registry trống. Chạy [bold]social-agent discover[/] để build sources.[/]"
            )
            return

        table = Table(
            title="📚 Source Registry",
            box=box.ROUNDED,
            border_style="cyan",
            show_lines=True,
        )
        table.add_column("Topic", style="bold yellow", no_wrap=True)
        table.add_column("Type", style="cyan", width=9)
        table.add_column("Source")
        table.add_column("✓", justify="right", style="green", width=4)
        table.add_column("✗", justify="right", style="red", width=4)
        table.add_column("Disc.", width=10, style="dim")

        icons = {"web_url": "🌐", "fb_page": "📘", "fb_group": "👥"}
        for r in rows:
            icon = icons.get(r["source_type"], "?")
            label = r.get("display_name") or r["identifier"]
            if len(label) > 45:
                label = label[:42] + "…"
            status = "" if r["is_active"] else " [dim](off)[/]"
            table.add_row(
                r["topic_id"],
                f"{icon} {r['source_type'].replace('_', ' ')}",
                label + status,
                str(r["success_count"]),
                str(r["fail_count"]),
                r["disc_date"] or "—",
            )

        console.print(table)
        console.print(
            f"\n[dim]Tổng {len(rows)} sources. --all để xem inactive. -t TOPIC để filter.[/]"
        )

    except Exception as e:
        console.print(f"[red]Lỗi:[/] {e}")
        sys.exit(1)
