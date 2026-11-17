"""The tools on a package with variants, the catalogue's layout from Phase 3b on, built in tmp_path: a
package `scenarios/SC97/` with its main file and its module, and the variants `SC97:a` and `SC97:b`, each
in `variants/<name>/` with an entry file that reads the package's main file.

The package runs as its variants: its main file is part of each variant's model, so it is no entry, and
the package is the owner of the records of its folder, which its variants read. The records of a folder
belong to that folder's owner. A pack or an adoption writes the records of one owner's folder, and every
other folder's records stay byte-identical."""

import json

from napkin.model.identity import COLLECTIONS
from tests.build import evidence_library, fixture_claim
from tests.evidence.test_adopt import linked
from tests.model.test_modules import CHANGE, TANKS, module, scenario
from tests.owned import write_family
from tools import catalogue
from tools.evidence import adopt, integrate

CITE = 'record {0}: source_transfer "Applied here."\n    claims:\n        {1}\n'
# An assumption that a model cites before a pack adds it.
LATER = 'record later: assumption {0} "A later assumption."\n'


def assumption(identifier):
    return {
        'id': identifier,
        'title': 'Later',
        'statement': 'The starting rate is an assumption.',
        'rationale': 'A fixture.',
        'status': 'selected',
        'origin': 'author',
        'review': {'status': 'unreviewed'},
        'supports': [],
        'evidence_needed': 'None: a fixture.',
        'decided': {'by': 'fixture', 'date': '2026-11-09'},
    }


def entry_text(later=None):
    """The package's main file, which uses the package's module: its tanks, the first resting on the
    assumption `later` that no folder holds yet."""
    body = TANKS
    if later is not None:
        body = body.replace('ask = 1 people/h  @fixture', 'ask = 1 people/h  @later')
    text = scenario(body=body + '\n' + CHANGE.format(20))
    return text + ('\n' + LATER.format(later) if later else '')


def variant_text(title, record, later=None):
    """A variant of the package: the second tank rests on `record` of the variant's own folder
    (`(name, claim)`), and the first on the assumption `later` that no folder holds yet."""
    lines = [f'variant "{title}"', '', 'change a2:', f'    ask = 2 people/h  @{record[0]}']
    if later is not None:
        lines += ['', 'change a1:', '    ask = 1 people/h  @later']
    text = '\n'.join(lines) + '\n'
    return text + '\n' + CITE.format(*record) + ('\n' + LATER.format(later) if later else '')


def nested(root, *, package_later=None, variant_later=None):
    """The package SC97 and its variants a and b below `root`, with the records of each folder: the
    package's source and claim, which its module cites, and each variant's own claim."""
    common = module().replace(
        'output total: people = sum(Tank.got)  @fixture', 'output total: people = sum(Tank.got)  @used'
    )
    files = write_family(
        root,
        {
            'SC97/common.scn': common + '\n' + CITE.format('used', 'C-USED'),
            'SC97/model.scn': entry_text(later=package_later),
            'SC97/variants/a/model.scn': variant_text('A', ('own', 'C-A'), variant_later),
            'SC97/variants/b/model.scn': variant_text('B', ('own', 'C-B')),
        },
    )
    owners = catalogue.owners(root)
    base, east, west = (owners[name].evidence for name in ('SC97', 'SC97:a', 'SC97:b'))
    (base / 'sources.json').write_text(json.dumps(evidence_library()['sources']))
    (base / 'claims.json').write_text(json.dumps([fixture_claim('C-USED')]))
    (base / 'assumptions.json').write_text(json.dumps([assumption('A-SHARED')]))
    (east / 'claims.json').write_text(json.dumps([fixture_claim('C-A')]))
    (west / 'claims.json').write_text(json.dumps([fixture_claim('C-B')]))
    return files


def records(root):
    """{owner: {file: bytes}} of the units and the evidence of each owner's folder."""
    return {
        name: {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in (owner.units, *(owner.evidence / f'{kind}.json' for kind in COLLECTIONS))
        }
        for name, owner in catalogue.owners(root).items()
    }


def everything(root):
    """{file: bytes} of every file below `root/scenarios`."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted((root / 'scenarios').rglob('*'))
        if path.is_file()
    }


def integrate_packs(root, *packs, write=True):
    folder = root / 'packs'
    folder.mkdir(exist_ok=True)
    for k, pack in enumerate(packs):
        (folder / f'pack-{k}.json').write_text(json.dumps(pack))
    args = ['--root', str(root), '--packs', str(folder), '--report', str(root / 'report.json')]
    return integrate.main([*args, *(['--write'] if write else [])])


def assumption_pack(owner, *upserts):
    return {
        'pack_version': '1',
        'kind': 'assumptions',
        'scenario': owner,
        'upsert': list(upserts),
        'retire': [],
    }


def ids(root, owner, kind):
    return [record['id'] for record in catalogue.locate(owner, root).collections()[kind]]


def test_the_package_and_its_variants_are_owners_read_as_their_files_say(tmp_path):
    nested(tmp_path)
    # The variants run; the package, which runs as its variants, owns the records of its folder.
    assert list(catalogue.entries(tmp_path)) == ['SC97:a', 'SC97:b']
    assert list(catalogue.owners(tmp_path)) == ['SC97:a', 'SC97:b', 'SC97']
    assert catalogue.readers(tmp_path) == {
        'SC97': ('SC97:a', 'SC97:b'),
        'SC97:a': ('SC97:a',),
        'SC97:b': ('SC97:b',),
    }


def test_a_variants_pack_writes_its_folder_and_leaves_the_package_and_its_sibling_alone(tmp_path):
    nested(tmp_path, variant_later='A-LATER')
    before, files = records(tmp_path), everything(tmp_path)
    assert integrate_packs(tmp_path, assumption_pack('SC97:a', assumption('A-LATER'))) == 0
    after = records(tmp_path)
    assert ids(tmp_path, 'SC97:a', 'assumptions') == ['A-LATER']
    assert after['SC97'] == before['SC97'] and after['SC97:b'] == before['SC97:b']
    # Only the records of the variant's own folder changed.
    changed = {path for path, content in everything(tmp_path).items() if files.get(path) != content}
    assert changed and changed <= set(before['SC97:a'])
    assert json.loads((tmp_path / 'report.json').read_text())['scenario'] == 'SC97:a'


def test_a_variants_pack_cannot_change_a_record_of_its_package(tmp_path, capsys):
    nested(tmp_path)
    files = everything(tmp_path)
    changed = {**assumption('A-SHARED'), 'statement': 'Changed by the pack of a variant.'}
    assert integrate_packs(tmp_path, assumption_pack('SC97:a', changed)) == 1
    assert 'A-SHARED' in capsys.readouterr().err
    assert everything(tmp_path) == files


def test_the_packages_pack_writes_its_folder_and_leaves_every_variant_alone(tmp_path):
    nested(tmp_path, package_later='A-ROOT')
    before, files = records(tmp_path), everything(tmp_path)
    # A dry run writes nothing; the write changes the package's records only.
    assert integrate_packs(tmp_path, assumption_pack('SC97', assumption('A-ROOT')), write=False) == 0
    assert everything(tmp_path) == files
    assert integrate_packs(tmp_path, assumption_pack('SC97', assumption('A-ROOT'))) == 0
    after = records(tmp_path)
    assert ids(tmp_path, 'SC97', 'assumptions') == ['A-SHARED', 'A-ROOT']
    assert after['SC97:a'] == before['SC97:a'] and after['SC97:b'] == before['SC97:b']
    changed = {path for path, content in everything(tmp_path).items() if files.get(path) != content}
    assert changed and changed <= set(before['SC97'])


def test_adopt_into_a_variant_writes_the_variants_folder_only(tmp_path):
    nested(tmp_path)
    # The sibling holds a record with its dependencies; their source is the package's.
    source = linked()
    west = catalogue.locate('SC97:b', tmp_path).evidence
    (west / 'claims.json').write_text(json.dumps([fixture_claim('C-B'), *source['claims']]))
    (west / 'assumptions.json').write_text(json.dumps(source['assumptions']))
    before, files = records(tmp_path), everything(tmp_path)
    args = ['--root', str(tmp_path), '--from', 'SC97:b', '--to', 'SC97:a', '--id', 'RT-FIXTURE']
    assert adopt.main(args) == 0
    assert everything(tmp_path) == files
    assert adopt.main([*args, '--write']) == 0
    after = records(tmp_path)
    assert ids(tmp_path, 'SC97:a', 'assumptions') == ['RT-FIXTURE']
    # The claims that the record depends on are copied; their source stays the package's.
    assert set(ids(tmp_path, 'SC97:a', 'claims')) == {'C-A', 'C-ACCESS', 'C-ACTION'}
    assert ids(tmp_path, 'SC97:a', 'sources') == []
    assert after['SC97'] == before['SC97'] and after['SC97:b'] == before['SC97:b']
    changed = {path for path, content in everything(tmp_path).items() if files.get(path) != content}
    assert changed and changed <= set(before['SC97:a'])
