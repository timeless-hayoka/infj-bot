"""Long-lived knowledge consumers must observe changes without a process restart."""
import json
from pathlib import Path
import shutil

from core import anchor_context


def make_repo(root: Path) -> Path:
    source = Path(__file__).resolve().parents[2] / 'ANCHOR' / 'knowledge_provider.py'
    assert source.is_file(), 'This contract test requires the sibling ANCHOR checkout'
    knowledge = root / 'knowledge'
    knowledge.mkdir(parents=True)
    shutil.copyfile(source, root / 'knowledge_provider.py')
    for slug in ('old', 'new'):
        (knowledge / f'{slug}.md').write_text(f'# {slug}\nContract topic')
    set_manifest(root, 'old')
    return root


def set_manifest(root: Path, slug: str) -> None:
    (root / 'knowledge/manifest.json').write_text(json.dumps({'version': 1, 'topics': [{'slug': slug}]}))


def test_manifest_refreshes_cached_topics(tmp_path, monkeypatch):
    root = make_repo(tmp_path / 'ANCHOR')
    monkeypatch.setenv('ANCHOR_ROOT', str(root))
    monkeypatch.setattr(anchor_context, '_knowledge_provider', None)
    assert anchor_context.list_anchor_repo_knowledge()[0]['slug'] == 'old'
    first = anchor_context.get_anchor_knowledge_provider()
    assert anchor_context.get_anchor_knowledge_provider() is first
    set_manifest(root, 'new')
    assert anchor_context.list_anchor_repo_knowledge()[0]['slug'] == 'new'
    assert anchor_context.get_anchor_repo_knowledge_topic('new')['content'].startswith('# new')
    assert anchor_context.get_anchor_repo_knowledge_topic('old') is None


def test_switching_checkouts_loads_exact_provider(tmp_path, monkeypatch):
    first = make_repo(tmp_path / 'first')
    second = make_repo(tmp_path / 'second')
    monkeypatch.setattr(anchor_context, '_knowledge_provider', None)
    monkeypatch.setenv('ANCHOR_ROOT', str(first))
    initial = anchor_context.get_anchor_knowledge_provider()
    source = second / 'knowledge_provider.py'
    source.write_text(source.read_text() + '\nKnowledgeProvider.contract_marker = "second"\n')
    monkeypatch.setenv('ANCHOR_ROOT', str(second))
    updated = anchor_context.get_anchor_knowledge_provider()
    assert updated.root == second / 'knowledge'
    assert updated.contract_marker == 'second'
    assert not hasattr(initial, 'contract_marker')
    source.write_text(source.read_text().replace('"second"', '"edited"'))
    assert anchor_context.get_anchor_knowledge_provider().contract_marker == 'edited'
