from pathlib import Path

from techwatch.stack import Use, image, inventory, matching

CATALOG = """
[versions]
spring = "5.3.39"
[libraries]
bom-spring = { module = "org.springframework:spring-framework-bom", version.ref = "spring" }
deltatom = { module = "fr.example:deltatom", version = "1.7.0" }
short = "com.example:short:2.0"
[plugins]
boot = { id = "org.springframework.boot", version = "4.1.2" }
"""

GRADLE = """
plugins { id("org.springframework.boot") version "4.1.2" }
dependencies { implementation("io.micrometer:micrometer-core:1.15.0") }
java { toolchain { languageVersion = JavaLanguageVersion.of(25) } }
"""

POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
<parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId>
<version>3.5.0</version></parent>
<properties><java.version>21</java.version><jersey.version>3.1.0</jersey.version></properties>
<dependencies>
<dependency><groupId>org.glassfish.jersey</groupId><artifactId>jersey-server</artifactId>
<version>${jersey.version}</version></dependency>
<dependency><groupId>x</groupId><artifactId>managed</artifactId></dependency>
</dependencies></project>"""

PYPROJECT = """
[project]
requires-python = ">=3.13"
dependencies = ["pydantic-ai>=2.0", "FastAPI[standard]"]
"""

UV_LOCK = """
[[package]]
name = "pydantic-ai"
version = "2.70.0"
"""

DOCKERFILE = """FROM node:24-alpine AS base
FROM base AS final
FROM ${JAVA_IMAGE}
FROM eclipse-temurin:25-jre-noble
"""

COMPOSE = """services:
  db:
    image: mongo:9.0.4@sha256:452bdaf2
  proxy:
    image: "nginx"
  app:
    image: ${APP_IMAGE:-registry/app}:${VERSION}
"""


def make_repo(root: Path) -> None:
    repo = root / "team" / "app"
    (repo / ".git").mkdir(parents=True)
    files = {
        "gradle/libs.versions.toml": CATALOG,
        "build.gradle.kts": GRADLE,
        "legacy/pom.xml": POM,
        "tools/pyproject.toml": PYPROJECT,
        "tools/uv.lock": UV_LOCK,
        "front/package.json": '{"dependencies": {"@angular/core": "^20.1.0"}}',
        "Dockerfile": DOCKERFILE,
        "docker-compose.yml": COMPOSE,
        "mise.toml": '[tools]\njava = "25"\n',
        ".tool-versions": "# pinned\nnodejs 22.11.0\n",
        "worker/Containerfile": "FROM python:3.13-slim\n",
        "front/node_modules/x/package.json": '{"dependencies": {"ignored": "1"}}',
        "broken/pom.xml": "<project>",
    }
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)


def test_inventory_reads_every_build_and_container_file(tmp_path: Path):
    make_repo(tmp_path)
    found = {(u.kind, u.name, u.version) for u in inventory([tmp_path])}
    assert found == {
        ("maven", "org.springframework:spring-framework-bom", "5.3.39"),
        ("maven", "fr.example:deltatom", "1.7.0"),
        ("maven", "com.example:short", "2.0"),
        ("maven", "org.springframework.boot", "4.1.2"),
        ("maven", "io.micrometer:micrometer-core", "1.15.0"),
        ("runtime", "java", "25"),
        ("maven", "org.springframework.boot:spring-boot-starter-parent", "3.5.0"),
        ("maven", "org.glassfish.jersey:jersey-server", "3.1.0"),
        ("runtime", "java", "21"),
        ("pypi", "pydantic-ai", "2.70.0"),
        ("pypi", "fastapi", "?"),
        ("runtime", "python", ">=3.13"),
        ("npm", "@angular/core", "^20.1.0"),
        ("image", "node", "24-alpine"),
        ("image", "eclipse-temurin", "25-jre-noble"),
        ("image", "mongo", "9.0.4"),
        ("image", "nginx", "latest"),
        ("runtime", "nodejs", "22.11.0"),
        ("image", "python", "3.13-slim"),
    }
    assert {u.repo for u in inventory([tmp_path])} == {"team/app"}


def test_matching_groups_repositories_by_version():
    uses = [
        Use("maven", "org.springframework.boot", "4.1.2", "vira", "build.gradle.kts"),
        Use("maven", "org.springframework.boot", "4.1.2", "loader", "build.gradle.kts"),
        Use("maven", "org.springframework.boot", "3.5.0", "legacy", "pom.xml"),
        Use("image", "nginx", "1.29", "proxy", "Dockerfile"),
    ]
    assert matching(uses, "Spring Boot") == {
        ("maven", "org.springframework.boot", "3.5.0"): ["legacy"],
        ("maven", "org.springframework.boot", "4.1.2"): ["loader", "vira"],
    }


def test_image_reference_forms():
    assert image("registry.example.com:5000/team/app:2.0.3") == ("registry.example.com:5000/team/app", "2.0.3")
    assert image("registry.example.com:5000/team/app") == ("registry.example.com:5000/team/app", "latest")
    assert image("${BASE}") is None
