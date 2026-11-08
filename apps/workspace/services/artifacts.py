"""Safe task artifacts: Markdown is stored as data, HTML is escaped before rendering."""

from html import escape
import re

from ..models import TaskArtifact


def create_artifact(run, kind, filename, content, fmt='markdown'):
    return TaskArtifact.objects.create(
        run=run, kind=kind, format=fmt, filename=filename, content=content,
    )


def _inline(text):
    escaped = escape(text)
    escaped = re.sub(r'`([^`]+)`', r'<code>\1</code>', escaped)
    escaped = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', escaped)
    return escaped


def markdown_to_html(title, markdown):
    """Small, dependency-free renderer. Raw HTML in documents is escaped."""
    lines = str(markdown or '').replace('\r', '').split('\n')
    out = [
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">',
        f'<title>{escape(title)}</title>',
        '<style>body{max-width:980px;margin:40px auto;padding:0 24px;'
        "font-family:'SimSun','宋体','STSong','Songti SC',serif;color:#1c3037;line-height:1.8}"
        'table{border-collapse:collapse;width:100%;margin:18px 0}th,td{border:1px solid #dfe8e5;'
        'padding:8px 10px;font-size:13px;vertical-align:top}th{background:#eef6f2}'
        'code{background:#f0f4f2;padding:2px 4px;border-radius:3px}'
        'pre{background:#f5f7f7;padding:14px;overflow:auto}'
        'blockquote{border-left:3px solid #9fc8b5;margin:16px 0;padding:6px 16px;color:#5f7a72}'
        '.meta{color:#7a898e;font-size:12px}</style></head><body>',
        f'<h1>{escape(title)}</h1>',
    ]
    i = 0
    in_list = False
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            if in_list:
                out.append('</ul>')
                in_list = False
            i += 1
            continue
        if stripped.startswith('```'):
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code.append(lines[i])
                i += 1
            out.append('<pre><code>' + escape('\n'.join(code)) + '</code></pre>')
            i += 1
            continue
        if stripped.startswith('|') and i + 1 < len(lines) and re.match(r'^\s*\|?\s*:?-{3,}', lines[i + 1]):
            header = [cell.strip() for cell in stripped.strip('|').split('|')]
            out.append('<table><thead><tr>' + ''.join(f'<th>{_inline(cell)}</th>' for cell in header) + '</tr></thead><tbody>')
            i += 2
            while i < len(lines) and lines[i].strip().startswith('|'):
                cells = [cell.strip() for cell in lines[i].strip().strip('|').split('|')]
                out.append('<tr>' + ''.join(f'<td>{_inline(cell)}</td>' for cell in cells) + '</tr>')
                i += 1
            out.append('</tbody></table>')
            continue
        heading = re.match(r'^(#{1,4})\s+(.+)$', stripped)
        if heading:
            if in_list:
                out.append('</ul>')
                in_list = False
            level = min(4, len(heading.group(1)) + 1)
            out.append(f'<h{level}>{_inline(heading.group(2))}</h{level}>')
            i += 1
            continue
        if stripped.startswith(('- ', '* ')):
            if not in_list:
                out.append('<ul>')
                in_list = True
            out.append(f'<li>{_inline(stripped[2:])}</li>')
            i += 1
            continue
        if stripped.startswith('> '):
            if in_list:
                out.append('</ul>')
                in_list = False
            out.append(f'<blockquote>{_inline(stripped[2:])}</blockquote>')
            i += 1
            continue
        if in_list:
            out.append('</ul>')
            in_list = False
        out.append(f'<p>{_inline(stripped)}</p>')
        i += 1
    if in_list:
        out.append('</ul>')
    out.append('</body></html>')
    return '\n'.join(out)
