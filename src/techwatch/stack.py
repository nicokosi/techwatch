"""Find which of your repositories use a library, image or runtime, and in which version.

    techwatch-stack spring-boot nginx      what matches each term, grouped by version
    techwatch-stack                        how much was found, per kind

Repositories are the git checkouts under TECHWATCH_CODE (colon-separated, default ~/Code).
Nothing is cached: the answer is the state of the working trees now.
"""

import argparse
import json
import os
import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "build", "target", "dist", ".gradle", ".idea", "__pycache__"}
MAX_DEPTH = 4  # build files deeper than this are fixtures or vendored code
GRADLE_DEP_RE = re.compile(r"""["']([\w.-]+):([\w.-]+):(\d[\w.+-]*)["']""")
GRADLE_PLUGIN_RE = re.compile(r"""id\s*\(?\s*["']([\w.-]+)["']\s*\)?\s+version\s+["'](\d[\w.+-]*)["']""")
JAVA_TOOLCHAIN_RE = re.compile(r"JavaLanguageVersion\.of\(\s*(\d+)\s*\)")
FROM_RE = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)", re.IGNORECASE | re.MULTILINE)
IMAGE_RE = re.compile(r"""^\s*image:\s*["']?([^"'\s#]+)""", re.MULTILINE)
POM = "{http://maven.apache.org/POM/4.0.0}"


@dataclass(frozen=True)
class Use:
    kind: str  # maven, npm, pypi, image, runtime
    name: str
    version: str
    repo: str
    file: str


def image(ref: str) -> tuple[str, str] | None:
    """`name:tag` of a container image, or None for a reference built from a variable."""
    if "$" in ref:
        return None
    ref = ref.split("@", 1)[0]
    name, _, tag = ref.rpartition(":") if ":" in ref.rsplit("/", 1)[-1] else (ref, "", "latest")
    return name, tag


def parse_catalog(text: str) -> list[tuple[str, str, str]]:
    data = tomllib.loads(text)
    versions = data.get("versions", {})
    found = []
    for section, kind in (("libraries", "maven"), ("plugins", "maven")):
        for entry in data.get(section, {}).values():
            if isinstance(entry, str):
                *coords, version = entry.split(":")
                found.append((kind, ":".join(coords), version))
                continue
            name = (
                entry.get("module")
                or entry.get("id")
                or ":".join(filter(None, [entry.get("group"), entry.get("name")]))
            )
            version = entry.get("version", "")
            if isinstance(version, dict):
                version = versions.get(version.get("ref"), "")
            if name and isinstance(version, str) and version:
                found.append((kind, name, version))
    return found


def parse_gradle(text: str) -> list[tuple[str, str, str]]:
    found = [("maven", f"{g}:{a}", v) for g, a, v in GRADLE_DEP_RE.findall(text)]
    found += [("maven", plugin, v) for plugin, v in GRADLE_PLUGIN_RE.findall(text)]
    found += [("runtime", "java", v) for v in JAVA_TOOLCHAIN_RE.findall(text)]
    return found


def parse_pom(text: str) -> list[tuple[str, str, str]]:
    if "<!DOCTYPE" in text:
        return []  # a pom needs no DTD; one in a checkout is not worth parsing
    root = ET.fromstring(text)
    ns = POM if root.tag.startswith(POM) else ""
    props = {p.tag.removeprefix(ns): (p.text or "").strip() for p in root.findall(f"{ns}properties/*")}

    def resolve(value: str) -> str:
        return re.sub(r"\$\{([^}]+)\}", lambda m: props.get(m.group(1), m.group(0)), value)

    found = []
    for dep in [root.find(f"{ns}parent"), *root.iter(f"{ns}dependency")]:
        if dep is None:
            continue
        version = resolve(dep.findtext(f"{ns}version", "").strip())
        if version and "$" not in version:
            found.append(
                ("maven", f"{dep.findtext(f'{ns}groupId', '')}:{dep.findtext(f'{ns}artifactId', '')}", version)
            )
    java = props.get("java.version") or props.get("maven.compiler.release") or props.get("maven.compiler.target")
    if java and "$" not in java:
        found.append(("runtime", "java", java))
    return found


def parse_pyproject(text: str, lock: str | None) -> list[tuple[str, str, str]]:
    project = tomllib.loads(text).get("project", {})
    locked = {p["name"]: p.get("version", "") for p in tomllib.loads(lock).get("package", [])} if lock else {}
    found = []
    for spec in project.get("dependencies", []):
        name = re.split(r"[\s\[<>=!~;@]", spec, maxsplit=1)[0].lower().replace("_", "-")
        constraint = re.sub(r"^\[[^]]*\]", "", spec[len(name) :].strip()).strip()
        found.append(("pypi", name, locked.get(name) or constraint or "?"))
    if python := project.get("requires-python"):
        found.append(("runtime", "python", python))
    return found


def parse_package_json(text: str) -> list[tuple[str, str, str]]:
    data = json.loads(text)
    return [("npm", n, v) for key in ("dependencies", "devDependencies") for n, v in data.get(key, {}).items()]


def parse_images(text: str, regex: re.Pattern) -> list[tuple[str, str, str]]:
    stages = {m.lower() for m in re.findall(r"\bAS\s+(\S+)", text, re.IGNORECASE)}
    found = []
    for ref in regex.findall(text):
        if ref.lower() not in stages and (parsed := image(ref)):
            found.append(("image", *parsed))
    return found


def parse_tools(name: str, text: str) -> list[tuple[str, str, str]]:
    if name == ".python-version":
        return [("runtime", "python", text.strip())]
    if name == "mise.toml":
        tools = tomllib.loads(text).get("tools", {})
        return [("runtime", tool, str(v)) for tool, v in tools.items() if isinstance(v, str | int | float)]
    rows = [line.split() for line in text.splitlines() if not line.lstrip().startswith("#")]
    return [("runtime", row[0], row[1]) for row in rows if len(row) >= 2]


def parse_file(path: Path) -> list[tuple[str, str, str]]:
    name, text = path.name, path.read_text(encoding="utf-8", errors="replace")
    if name == "libs.versions.toml":
        return parse_catalog(text)
    if name in ("build.gradle.kts", "build.gradle", "settings.gradle.kts"):
        return parse_gradle(text)
    if name == "pom.xml":
        return parse_pom(text)
    if name == "pyproject.toml":
        lock = path.with_name("uv.lock")
        return parse_pyproject(text, lock.read_text(encoding="utf-8") if lock.exists() else None)
    if name == "package.json":
        return parse_package_json(text)
    if name.startswith(("Dockerfile", "Containerfile")):
        return parse_images(text, FROM_RE)
    if re.match(r"(docker-)?compose.*\.ya?ml$", name):
        return parse_images(text, IMAGE_RE)
    if name in (".python-version", "mise.toml", ".tool-versions"):
        return parse_tools(name, text)
    return []


def repositories(root: Path) -> list[Path]:
    """Git checkouts under root, two levels deep at most (root/repo and root/group/repo)."""

    def children(folder: Path) -> list[Path]:
        try:
            return sorted(c for c in folder.iterdir() if c.is_dir() and not c.name.startswith("."))
        except OSError:
            return []  # an unreadable folder (a database volume owned by a container) hides only itself

    found = []
    for child in children(root):
        if (child / ".git").exists():
            found.append(child)
        else:
            found += [g for g in children(child) if (g / ".git").exists()]
    return found


def scan(repo: Path, label: str) -> list[Use]:
    uses = []
    for folder, dirs, files in os.walk(repo, onerror=lambda _: None):
        depth = len(Path(folder).relative_to(repo).parts)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".") and depth < MAX_DEPTH]
        for name in files:
            path = Path(folder) / name
            try:
                found = parse_file(path)
            except (OSError, ValueError, ET.ParseError, KeyError, TypeError, AttributeError):
                continue  # one unreadable build file must not hide the others
            uses += [Use(k, n, v, label, str(path.relative_to(repo))) for k, n, v in found]
    return uses


def inventory(roots: list[Path]) -> list[Use]:
    return [use for root in roots for repo in repositories(root) for use in scan(repo, str(repo.relative_to(root)))]


def matching(uses: list[Use], term: str) -> dict[tuple[str, str, str], list[str]]:
    """(kind, name, version) -> repositories, for every use whose name holds each word of the
    term: "Spring Boot" finds org.springframework.boot as well as spring-boot-starter-web."""
    words = [w for w in re.split(r"[\s._:/-]+", term.lower()) if w]
    groups: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for use in uses:
        if words and all(w in use.name.lower() for w in words):
            groups[(use.kind, use.name, use.version)].add(use.repo)
    return {key: sorted(repos) for key, repos in sorted(groups.items())}


def roots_from_env() -> list[Path]:
    return [Path(p).expanduser() for p in os.environ.get("TECHWATCH_CODE", "~/Code").split(":") if p]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("terms", nargs="*", help="parts of a library, image or runtime name")
    args = parser.parse_args()
    uses = inventory(roots_from_env())
    if not args.terms:
        repos = {u.repo for u in uses}
        counts = defaultdict(int)
        for use in uses:
            counts[use.kind] += 1
        print(f"{len(repos)} repositories: " + ", ".join(f"{n} {k}" for k, n in sorted(counts.items())))
        return 0
    for term in args.terms:
        groups = matching(uses, term)
        print(f"## {term}: " + ("nothing" if not groups else f"{len(groups)} versions"))
        for (kind, name, version), repos in groups.items():
            print(f"{kind} {name} {version}: {', '.join(repos)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
