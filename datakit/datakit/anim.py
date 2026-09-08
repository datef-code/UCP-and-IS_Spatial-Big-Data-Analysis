"""动画产物：matplotlib FuncAnimation → mp4 → **自包含 HTML**（video base64 内嵌）。

为什么不用 plotly 帧动画
------------------------
plotly 的 ``go.Frame`` 会把每一帧的点重复写进 HTML：30 万点 × 32 帧就是几十 MB，
播放还容易卡。改成 **mp4 + ``<video>``** 之后：

* 体积降一个数量级（同样内容约 1–2 MB）；
* 浏览器原生解码，播放丝滑，带进度条 / 倍速 / 全屏；
* 依然是**单文件自包含**——mp4 以 base64 内嵌，离线可开、挪动不丢。

用法（与 ``datakit.report`` / ``datakit.write_*`` 同层）：:

    fig, ax = plt.subplots()
    def draw(i): ...                      # 第 i 帧怎么画
    mp4 = dk.animate(OUT / "demo.mp4", fig, draw, n_frames=64, fps=12)
    html = dk.video_page(mp4, title="...", subtitle="...", caption="...",
                         source="05_map/output/...", alt_text="...")
    (OUT / "demo.html").write_text(html, encoding="utf-8")

依赖：``matplotlib`` + ``imageio-ffmpeg``（``uv sync --extra viz``）。
"""
from __future__ import annotations

import base64
import datetime as _dt
import shutil
from pathlib import Path
from typing import Callable, Iterable

__all__ = ["animate", "video_page", "ffmpeg_available"]


def ffmpeg_available() -> bool:
    """mp4 编码是否可用（需要 imageio-ffmpeg 或系统 ffmpeg）。"""
    try:
        import imageio_ffmpeg  # noqa: F401
        return True
    except Exception:
        return bool(shutil.which("ffmpeg"))


def animate(
    out_path: Path,
    fig,
    draw: Callable[[int], None],
    n_frames: int,
    fps: int = 12,
    bitrate: int = 1800,
    dpi: int = 110,
) -> Path:
    """把 ``draw(i)`` 的每一帧渲染成 mp4。

    Parameters
    ----------
    out_path : 输出 mp4 路径（父目录会自动创建）
    fig : ``matplotlib.figure.Figure``，由调用方创建并负责坐标轴
    draw : ``draw(i)`` 绘制第 i 帧（原地重绘，不需要返回 artist）
    n_frames : 总帧数
    fps : 帧率
    bitrate : 码率（kbps）；越小体积越小
    dpi : 渲染分辨率
    """
    import matplotlib as mpl
    from matplotlib import animation

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    writer = None
    try:
        import imageio_ffmpeg
        mpl.rcParams["animation.ffmpeg_path"] = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    try:
        writer = animation.FFMpegWriter(fps=fps, bitrate=bitrate)
    except Exception as exc:                       # pragma: no cover
        raise RuntimeError(
            "mp4 编码需要 ffmpeg：pip install imageio-ffmpeg（或系统安装 ffmpeg）"
        ) from exc

    anim = animation.FuncAnimation(fig, draw, frames=int(n_frames), interval=1000 / fps)
    anim.save(str(out_path), writer=writer, dpi=dpi)
    return out_path


def video_page(
    mp4: Path,
    *,
    title: str,
    subtitle: str = "",
    caption: str = "",
    source: str = "",
    alt_text: str = "",
    width: int = 980,
    poster_note: str = "",
) -> str:
    """把 mp4 包成一个自包含 HTML 页面（base64 内嵌 + 下载按钮）。

    遵循规范 §8.8.4「每图必带 7 项信息」：标题是结论、口径与样本量进副标题、
    来源产物路径进脚注、alt_text 供无障碍阅读复用。
    """
    mp4 = Path(mp4)
    b64 = base64.b64encode(mp4.read_bytes()).decode("ascii")
    size_mb = mp4.stat().st_size / 1e6
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
:root{{--ink:#111827;--sub:#6B7280;--line:#E5E7EB}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif;
     color:var(--ink);background:#fff;line-height:1.75}}
.wrap{{max-width:{width}px;margin:0 auto;padding:34px 24px 80px}}
h1{{font-size:24px;margin:0 0 6px;letter-spacing:-.3px}}
.sub{{color:var(--sub);font-size:13.5px;margin:0 0 16px}}
.player{{border:1px solid var(--line);border-radius:12px;overflow:hidden;background:#000}}
video{{width:100%;display:block}}
.cap{{font-size:12.5px;color:var(--sub);padding:10px 14px;background:#FAFAFA;
     border-top:1px solid var(--line)}}
.dl{{display:inline-block;margin-top:12px;font-size:13px;text-decoration:none;
    color:var(--ink);border:1px solid var(--line);border-radius:999px;padding:6px 14px}}
.dl:hover{{border-color:#D55E00;color:#D55E00}}
.foot{{margin-top:14px;font-size:12px;color:var(--sub)}}
</style></head><body><div class="wrap">
<h1>{title}</h1>
<p class="sub">{subtitle}</p>
<div class="player">
  <video controls autoplay loop muted playsinline
         aria-label="{alt_text or title}">
    <source src="data:video/mp4;base64,{b64}" type="video/mp4">
    你的浏览器不支持 HTML5 视频，请下载后观看。
  </video>
</div>
<a class="dl" href="data:video/mp4;base64,{b64}" download="{mp4.name}">⬇ 下载 mp4（{size_mb:.1f} MB）</a>
{f'<p class="cap">{caption}</p>' if caption else ''}
<p class="foot">数据来源：{source}　|　生成脚本 09_interactive　|　生成时间 {now}
{('　|　' + poster_note) if poster_note else ''}</p>
</div></body></html>"""
