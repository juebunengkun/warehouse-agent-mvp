from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

KEY_TERMS = [
    "ODS",
    "DWD",
    "DWS",
    "ADS",
    "销售额",
    "订单数",
    "支付用户数",
    "客单价",
    "转化率",
    "日期",
    "地区",
    "渠道",
    "商品",
    "用户",
    "分区",
    "非空",
    "唯一",
    "波动",
    "T+1",
    "日",
    "日报",
]


@dataclass
class DocumentChunk:
    id: str
    title: str
    source: str
    text: str


def _tokenize(text: str) -> set[str]:
    lowered = text.lower()
    tokens = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*|\d+", lowered))
    for term in KEY_TERMS:
        if term.lower() in lowered or term in text:
            tokens.add(term.lower())
    return tokens


def _split_markdown(path: Path) -> list[DocumentChunk]:
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^##\s+", text)
    chunks: list[DocumentChunk] = []

    for index, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        if index == 0 and part.startswith("#"):
            title = part.splitlines()[0].lstrip("#").strip()
            body = part
        else:
            lines = part.splitlines()
            title = lines[0].strip()
            body = "## " + part
        chunks.append(
            DocumentChunk(
                id=f"{path.name}:{index}",
                title=title,
                source=path.name,
                text=body,
            )
        )
    return chunks


def _split_json(path: Path) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    if path.name == "table_metadata.json":
        from dw_agent.metadata import LocalJsonMetadataProvider

        tables = LocalJsonMetadataProvider(path.parent).list_tables()
        for table in tables:
            name = table.get("name", "unknown_table")
            text = json.dumps(table, ensure_ascii=False, indent=2)
            chunks.append(
                DocumentChunk(
                    id=f"{path.name}:{name}",
                    title=f"琛ㄧ粨鏋?{name}",
                    source=path.name,
                    text=text,
                )
            )
        return chunks

    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("tables"), list):
        for table in data["tables"]:
            name = table.get("name", "unknown_table")
            text = json.dumps(table, ensure_ascii=False, indent=2)
            chunks.append(
                DocumentChunk(
                    id=f"{path.name}:{name}",
                    title=f"表结构 {name}",
                    source=path.name,
                    text=text,
                )
            )
    else:
        chunks.append(
            DocumentChunk(
                id=path.name,
                title=path.stem,
                source=path.name,
                text=json.dumps(data, ensure_ascii=False, indent=2),
            )
        )
    return chunks


class KnowledgeBase:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.chunks = self._load()

    def _load(self) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []
        for path in sorted(self.root.glob("*")):
            if path.suffix.lower() == ".md":
                chunks.extend(_split_markdown(path))
            elif path.suffix.lower() == ".json":
                chunks.extend(_split_json(path))
        return chunks

    def search(self, query: str, top_k: int = 4) -> list[dict]:
        query_tokens = _tokenize(query)
        scored: list[tuple[int, DocumentChunk]] = []

        for chunk in self.chunks:
            chunk_tokens = _tokenize(chunk.title + "\n" + chunk.text)
            overlap = query_tokens & chunk_tokens
            phrase_hits = sum(2 for token in query_tokens if token and token in chunk.text.lower())
            score = len(overlap) * 3 + phrase_hits
            if score > 0:
                scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                "id": chunk.id,
                "title": chunk.title,
                "source": chunk.source,
                "score": score,
                "excerpt": _excerpt(chunk.text),
            }
            for score, chunk in scored[:top_k]
        ]


def _excerpt(text: str, limit: int = 420) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."
