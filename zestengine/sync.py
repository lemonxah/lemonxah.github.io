#!/usr/bin/env python3
"""Copy the ZestEngine guides from the engine repository into this book's `src/`.

    ./sync.py [path-to-zestengine-repo]        (default: ~/storage/git/zestengine)

The guides are written and tested next to the engine code (the examples in ECS.md are compiled by
`cargo test -p zestengine-core --test ecs_guide`), so the engine repository stays the source of truth.
This script makes standalone copies the book can build without that checkout:

* whole guides are copied as they are;
* README.md is cut into pages by section heading;
* relative links are rewritten: a link to another published page points at the page, anything else
  (source files, crates, the license) points at the file on GitHub;
* pages that describe the replaced `ComponentCtx` API are deliberately not published (see SKIPPED);
* the old `Script` component and the unused `zestengine-scripting` prototype are cut out of the WASM
  guide and the README pages (see clean_wasm / clean_readme): only the ECS and `Wasm Script` are current.

Hand-written pages (index.md, ecs-tutorial.md, ecs-cheatsheet.md, api.md, SUMMARY.md) are never touched.
"""
import os
import re
import shutil
import sys

REPO_URL = "https://github.com/lemonxah/zestengine"
BRANCH = "main"

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
ENGINE = os.path.abspath(os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/storage/git/zestengine"))

# repo path -> page in src/ (flat, so a link between two pages is just a file name)
GUIDES = {
    "ECS.md": "ECS.md",
    "ENGINE_API.md": "ENGINE_API.md",
    "WASM.md": "WASM.md",
    "docs/shaders.md": "shaders.md",
    "docs/shaders-unity-compat.md": "shaders-unity-compat.md",
    "docs/user-content.md": "user-content.md",
    "docs/modding.md": "modding.md",
    "docs/vr-avatars.md": "vr-avatars.md",
    "docs/dedicated-server.md": "dedicated-server.md",
    "docs/deployment/dedicated-server.md": "deploy-dedicated-server.md",
    "docs/importing-megascans-fab.md": "importing-packs.md",
}

# Not published, and why. Links to them fall back to the file on GitHub.
SKIPPED = {
    "docs/components.md": "documents ComponentCtx, which the ECS (see ECS.md) replaced",
    "docs/networking.md": "its code samples use ComponentCtx; ENGINE_API.md#networking is current",
    "docs/default-assets.md": "an internal working checklist, not documentation",
}

# README.md sections -> pages. (page, title, [section headings], heading shift)
README_PAGES = [
    ("overview.md", "What is ZestEngine", ["__intro__", "Stack", "Workspace layout"], 0),
    ("features.md", "Features and roadmap", ["Features", "Planned", "Roadmap (milestones)"], 0),
    ("flux.md", "Flux: realtime global illumination", ["Flux — realtime global illumination"], None),
    ("getting-started.md", "Getting started", ["Running"], -1),
    ("license.md", "License and attribution", ["License and attribution"], None),
]

IMAGES = {"crates/zestengine-assets/zestengine.jpg": "images/zestengine.jpg"}

# Links in the README/guides to these repo files point at the matching book page.
LINK_ALIASES = {"README.md": "index.md"}

warnings = []


def read(rel):
    with open(os.path.join(ENGINE, rel), encoding="utf-8") as f:
        return f.read()


def write(dest, text):
    path = os.path.join(SRC, dest)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"  wrote src/{dest}")


def split_code(text):
    """Yield (is_code, chunk) so rewriting never touches fenced code blocks."""
    out, buf, fenced = [], [], False
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            if fenced:
                buf.append(line)
                out.append((True, "".join(buf)))
                buf, fenced = [], False
            else:
                if buf:
                    out.append((False, "".join(buf)))
                buf, fenced = [line], True
        else:
            buf.append(line)
    if buf:
        out.append((fenced, "".join(buf)))
    return out


LINK = re.compile(r'(!?\[[^\]\n]*\])\(([^)\s]+)((?:\s+"[^"]*")?)\)')


def rewrite_links(text, src_repo_path, dest_page):
    """Point relative links at book pages or at GitHub."""
    dest_dir = os.path.dirname(dest_page)
    src_dir = os.path.dirname(src_repo_path)

    def fix(match):
        label, target, title = match.groups()
        if re.match(r"^([a-z][a-z0-9+.-]*:|#|/)", target, re.I):
            return match.group(0)
        path, _, anchor = target.partition("#")
        anchor = "#" + anchor if anchor else ""
        resolved = os.path.normpath(os.path.join(src_dir, path))
        page = IMAGES.get(resolved) or GUIDES.get(resolved) or LINK_ALIASES.get(resolved)
        if page:
            return f"{label}({os.path.relpath(page, dest_dir or '.')}{anchor}{title})"
        full = os.path.join(ENGINE, resolved)
        if os.path.isfile(full):
            return f"{label}({REPO_URL}/blob/{BRANCH}/{resolved}{anchor}{title})"
        if os.path.isdir(full):
            return f"{label}({REPO_URL}/tree/{BRANCH}/{resolved}{anchor}{title})"
        warnings.append(f"{src_repo_path}: link to missing file {resolved!r}; kept as plain text")
        return label[label.index("[") + 1:-1] if not label.startswith("!") else ""

    chunks = []
    for is_code, chunk in split_code(text):
        if is_code:
            chunks.append(chunk)
        else:
            # leave `inline code` alone
            parts = chunk.split("`")
            for i in range(0, len(parts), 2):
                parts[i] = LINK.sub(fix, parts[i])
            chunks.append("`".join(parts))
    return "".join(chunks)


def drop_section(text, heading):
    """Remove the section that starts at the line `heading` (e.g. '## Foo') up to the next heading of
    the same or a higher level. Stops the sync if the heading is not there, so a stale cut is noticed."""
    level = len(heading) - len(heading.lstrip("#"))
    lines, out, skipping, fenced, found = text.splitlines(keepends=True), [], False, False, False
    for line in lines:
        if line.lstrip().startswith("```"):
            fenced = not fenced
        m = re.match(r"^(#{1,6}) ", line) if not fenced else None
        if m and line.strip() == heading:
            skipping, found = True, True
            continue
        if skipping and m and len(m.group(1)) <= level:
            skipping = False
        if not skipping:
            out.append(line)
    if not found:
        sys.exit(f"sync.py: heading {heading!r} not found; the engine docs changed, update the cleanup")
    return "".join(out)


def cut(text, old, new=""):
    """Replace `old` exactly once, or stop the sync."""
    if text.count(old) != 1:
        sys.exit(f"sync.py: expected exactly one {old[:60]!r}; the engine docs changed, update the cleanup")
    return text.replace(old, new)


def drop_last_column(text, header_cell):
    """Remove the last column of the table whose header row contains `header_cell`."""
    out, in_table, found = [], False, False
    for line in text.splitlines(keepends=True):
        if not in_table and line.startswith("|") and header_cell in line:
            in_table, found = True, True
        elif in_table and not line.startswith("|"):
            in_table = False
        if in_table:
            cells = line.rstrip("\n").rstrip().rstrip("|").rsplit("|", 1)[0]
            line = cells + "|\n"
        out.append(line)
    if not found:
        sys.exit(f"sync.py: no table with {header_cell!r}; the engine docs changed, update the cleanup")
    return "".join(out)


def clean_wasm(text):
    """Publish only the current WASM component (`Wasm Script`). The older `Script` component (`env`
    imports) is a prototype that packages and mods reject, and `zestengine-scripting` is not used."""
    for heading in ("### The two component types", "### Which one to use", "### The zestengine-scripting crate"):
        text = drop_section(text, heading)
    text = cut(
        text,
        "## Quick start\n",
        "### The Wasm Script component\n\n"
        "WASM modules run through the `Wasm Script` component (`WasmScript`, source "
        "`crates/zestengine-core/src/wasm/`). A module imports from the module `host` and exports "
        "`zest_invoke`, `zest_read_property` and an optional `zest_update`. It declares its actions, "
        "properties and capabilities in a `zest_manifest` custom section, so they show up in the editor's "
        "binding dropdowns next to the built-in components. Its state lives in its own linear memory (it is "
        "not saved with the scene), it hot-reloads when its file changes (polled every 0.5 s), and content "
        "packages and mods accept it. Each entry-point call gets 5 M units of fuel for a project module and "
        "1 M for an untrusted one.\n\n"
        "## Quick start\n",
    )
    text = drop_section(text, "## The legacy Script component")
    text = drop_section(text, "### Legacy Script exports and imports")
    text = drop_last_column(text, "Legacy `Script`")
    text = "".join(l for l in text.splitlines(keepends=True) if not l.startswith("| Legacy `Script` |"))
    text = cut(text, "(29 `wasm` and 8 `script` tests pass)", "(the `wasm` unit tests pass)")
    text = cut(text, "a mod's scenes may not use the legacy `Script` component; ", "")
    text = cut(text, "cargo test -p zestengine-core --lib --locked script    # legacy Script and mod-permission tests\n", "")
    text = cut(text, " Legacy `Script` failures are not logged at all.", "")
    text = cut(text, ", except the legacy `env` ones", "")
    left = [l for l in text.splitlines() if re.search(r"legacy|zestengine-scripting|script\.rs|`env`", l, re.I)]
    if left:
        sys.exit("sync.py: old-API wording still in WASM.md:\n  " + "\n  ".join(l[:140] for l in left))
    return text


def clean_readme_page(page, text):
    """Drop README sentences about removed or unused machinery."""
    if page == "overview.md":
        text = cut(text, "  zestengine-scripting WASM host (consolidation with core integration pending)\n", "")
    if page == "features.md":
        text = cut(text, "; the old component lifecycle callbacks and context dispatcher are removed", "")
        text = cut(text, ", never the legacy callback lookup cache", "")
        text = cut(text, " The older `Script`\n  component (`env` imports) is a prototype that packages and mods reject.", "")
    left = [l for l in text.splitlines() if re.search(r"legacy|ComponentCtx|older `Script`|zestengine-scripting", l, re.I)]
    if left:
        sys.exit(f"sync.py: old-API wording still in {page}:\n  " + "\n  ".join(l[:140] for l in left))
    return text


def header(src_repo_path):
    return (
        f"<!-- Copied from {src_repo_path} in the engine repository by sync.py. "
        f"Edit it there, then run ./sync.py. -->\n\n"
    )


def sections(text):
    """README -> {heading: body}, with '__intro__' for everything between the title and the first ##."""
    out, name, buf, fenced = {}, "__intro__", [], False
    lines = text.splitlines(keepends=True)
    for line in lines[1:]:  # skip the "# zestengine" title
        if line.lstrip().startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("## "):
            out[name] = "".join(buf).strip("\n")
            name, buf = line[3:].strip(), []
        else:
            buf.append(line)
    out[name] = "".join(buf).strip("\n")
    return out


def shift(text, delta):
    """Move markdown headings up (-1) or down (+1) a level, outside code blocks."""
    if not delta:
        return text
    out = []
    for is_code, chunk in split_code(text):
        if not is_code:
            chunk = re.sub(
                r"^(#{1,6}) ", lambda m: "#" * max(1, len(m.group(1)) + delta) + " ", chunk, flags=re.M
            )
        out.append(chunk)
    return "".join(out)


def main():
    if not os.path.isfile(os.path.join(ENGINE, "ECS.md")):
        sys.exit(f"{ENGINE} does not look like the zestengine repository (no ECS.md)")
    print(f"syncing from {ENGINE}")

    for repo_path, dest in GUIDES.items():
        text = read(repo_path)
        if repo_path == "WASM.md":
            text = clean_wasm(text)
        text = rewrite_links(text, repo_path, dest)
        write(dest, header(repo_path) + text)

    readme = read("README.md")
    parts = sections(readme)
    for page, title, wanted, level in README_PAGES:
        body = []
        for name in wanted:
            if name not in parts:
                sys.exit(f"README.md has no section {name!r}; update README_PAGES in sync.py")
            text = parts[name]
            if name == "__intro__":
                body.append(text)
            elif level is None:
                body.append(text)  # the page holds a single section: its heading becomes the title
            else:
                body.append(f"## {name}\n\n{shift(text, level)}" if level == 0 else shift(text, level))
        content = f"# {title}\n\n" + "\n\n".join(b for b in body if b.strip()) + "\n"
        content = rewrite_links(content, "README.md", page)
        # The README says "see below" for Flux; here it is a page of its own.
        content = content.replace("(**Flux** — see below)", "(**[Flux](flux.md)**)")
        content = clean_readme_page(page, content)
        write(page, header("README.md") + content)

    for repo_path, dest in IMAGES.items():
        target = os.path.join(SRC, dest)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(os.path.join(ENGINE, repo_path), target)
        print(f"  copied src/{dest}")

    print("not published:")
    for path, why in SKIPPED.items():
        print(f"  {path}: {why}")
    for w in warnings:
        print("warning:", w)


if __name__ == "__main__":
    main()
